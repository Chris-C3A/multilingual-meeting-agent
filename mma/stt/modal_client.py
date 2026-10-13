"""Client for the Modal STT app (modal_app/app.py).

Protocol:
  POST <submit_url>?language=..&diarize=..&num_speakers=..   multipart field `file`
       -> 200 {"call_id": "fc-..."}
  GET  <result_url>?call_id=fc-...
       -> 202 {"status": "processing"}   keep polling
       -> 200 {transcript JSON}           done

Large video files are shrunk locally (audio track only, ffmpeg) before upload,
so we don't ship hundreds of MB of video frames to a speech model.
"""

from __future__ import annotations

import mimetypes
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from mma.config import STTConfig

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # ~25 MB: above this, extract audio from video

VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".3gp",
     ".ts"}
)


class STTError(RuntimeError):
    """The STT service rejected the request or the job failed."""


class STTTimeoutError(STTError, TimeoutError):
    """The transcript was not ready within poll_timeout."""


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def should_extract_audio(path: Path, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> bool:
    """True for video files larger than `max_upload_bytes`."""
    return is_video(path) and path.stat().st_size > max_upload_bytes


def ffmpeg_extract_cmd(src: Path, dst: Path) -> list[str]:
    # 16 kHz mono matches what the server normalizes to anyway; AAC at 64 kbps
    # keeps an hour of speech under ~30 MB.
    return [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "64k",
        str(dst),
    ]


def extract_audio(src: Path, dst: Path) -> Path:
    """Write the audio track of `src` to `dst` (.m4a) with ffmpeg."""
    if shutil.which("ffmpeg") is None:
        raise STTError("ffmpeg is required to extract audio from large video files")
    proc = subprocess.run(ffmpeg_extract_cmd(src, dst), capture_output=True, text=True)
    if proc.returncode != 0:
        raise STTError(f"ffmpeg failed on {src.name}: {proc.stderr.strip()[-500:]}")
    return dst


@dataclass
class ModalSTTClient:
    submit_url: str
    result_url: str
    language: str = "ar"
    diarize: bool = True
    num_speakers: int | None = None
    poll_interval: float = 10.0
    poll_timeout: float = 3600.0
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    http: httpx.Client | None = None
    # Injectable for tests.
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        if not self.submit_url or not self.result_url:
            raise STTError(
                "submit_url and result_url are required "
                "(set stt.submit_url / stt.result_url or MMA_STT_SUBMIT_URL / MMA_STT_RESULT_URL)"
            )
        if self.http is None:
            # Uploads of long meetings can be slow; polls are quick.
            self.http = httpx.Client(timeout=httpx.Timeout(30.0, read=300.0, write=300.0))

    @classmethod
    def from_config(cls, stt: STTConfig, **overrides: Any) -> ModalSTTClient:
        kwargs: dict[str, Any] = {
            "submit_url": stt.submit_url,
            "result_url": stt.result_url,
            "language": stt.language,
            "diarize": stt.diarize,
            "num_speakers": stt.num_speakers,
            "poll_interval": stt.poll_interval,
            "poll_timeout": stt.poll_timeout,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    # ── public API ───────────────────────────────────────────────────────────
    def transcribe(self, path: str | Path) -> dict:
        """Upload `path`, wait for the job, return the transcript JSON."""
        return self.wait(self.submit(path))

    def submit(self, path: str | Path) -> str:
        """Upload a file and return the job's call_id."""
        path = Path(path)
        if not path.is_file():
            raise STTError(f"no such file: {path}")

        if should_extract_audio(path, self.max_upload_bytes):
            with tempfile.TemporaryDirectory(prefix="mma-") as tmp:
                audio = extract_audio(path, Path(tmp) / f"{path.stem}.m4a")
                return self._upload(audio)
        return self._upload(path)

    def wait(self, call_id: str) -> dict:
        """Poll the result endpoint until 200 (done) or poll_timeout elapses."""
        deadline = self.clock() + self.poll_timeout
        last_error: Exception | None = None
        while True:
            try:
                resp = self.http.get(self.result_url, params={"call_id": call_id})
            except httpx.TransportError as exc:  # transient network issue: keep polling
                last_error = exc
            else:
                last_error = None
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code != 202:
                    raise STTError(
                        f"result for {call_id} failed: HTTP {resp.status_code}: {_snippet(resp)}"
                    )

            remaining = deadline - self.clock()
            if remaining <= 0:
                msg = f"transcript {call_id} not ready after {self.poll_timeout:g}s"
                if last_error is not None:
                    msg += f" (last error: {last_error})"
                raise STTTimeoutError(msg)
            self.sleep(min(self.poll_interval, remaining))

    # ── internals ────────────────────────────────────────────────────────────
    def _params(self) -> dict[str, str]:
        params = {"language": self.language, "diarize": "true" if self.diarize else "false"}
        if self.num_speakers:
            params["num_speakers"] = str(self.num_speakers)
        return params

    def _upload(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            try:
                resp = self.http.post(
                    self.submit_url,
                    params=self._params(),
                    files={"file": (path.name, fh, mime)},
                )
            except httpx.HTTPError as exc:
                raise STTError(f"upload of {path.name} failed: {exc}") from exc
        if resp.status_code != 200:
            raise STTError(f"submit failed: HTTP {resp.status_code}: {_snippet(resp)}")
        try:
            return resp.json()["call_id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise STTError(f"submit returned no call_id: {_snippet(resp)}") from exc


def _snippet(resp: httpx.Response, limit: int = 300) -> str:
    text = resp.text.strip()
    return text if len(text) <= limit else text[:limit] + "..."
