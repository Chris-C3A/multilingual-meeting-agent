import json
import shutil
import subprocess

import httpx
import pytest

from mma.config import STTConfig
from mma.stt import modal_client
from mma.stt.modal_client import ModalSTTClient, STTError, STTTimeoutError

SUBMIT = "https://stt.invalid/submit"
RESULT = "https://stt.invalid/result"
TRANSCRIPT = {"text": "hello مرحبا", "segments": [], "diarized": True}


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make_client(handler, **kw):
    ft = FakeTime()
    client = ModalSTTClient(
        submit_url=SUBMIT,
        result_url=RESULT,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=ft.sleep,
        clock=ft.clock,
        **kw,
    )
    return client, ft


def scripted(results):
    """Handler: POST /submit -> call_id; GET /result -> next status from `results`."""
    seen = {"posts": [], "gets": []}
    it = iter(results)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["posts"].append(request)
            return httpx.Response(200, json={"call_id": "fc-123"})
        seen["gets"].append(request)
        status = next(it)
        if isinstance(status, Exception):
            raise status
        if status == 202:
            return httpx.Response(202, json={"status": "processing"})
        if status == 200:
            return httpx.Response(200, json=TRANSCRIPT)
        return httpx.Response(status, text="boom")

    return handler, seen


@pytest.fixture
def audio(tmp_path):
    p = tmp_path / "meeting.m4a"
    p.write_bytes(b"\x00" * 1024)
    return p


def test_polls_202_202_200(audio):
    handler, seen = scripted([202, 202, 200])
    client, ft = make_client(handler, poll_interval=5)

    assert client.transcribe(audio) == TRANSCRIPT
    assert len(seen["gets"]) == 3
    assert ft.sleeps == [5, 5]
    assert all(r.url.params["call_id"] == "fc-123" for r in seen["gets"])


def test_submit_sends_file_and_params(audio):
    handler, seen = scripted([200])
    client, _ = make_client(handler, language="en", num_speakers=4, diarize=False)
    client.transcribe(audio)

    (post,) = seen["posts"]
    assert str(post.url).startswith(SUBMIT)
    assert post.url.params["language"] == "en"
    assert post.url.params["num_speakers"] == "4"
    assert post.url.params["diarize"] == "false"
    body = post.read()
    assert b'name="file"; filename="meeting.m4a"' in body


def test_num_speakers_omitted_by_default(audio):
    handler, seen = scripted([200])
    client, _ = make_client(handler)
    client.transcribe(audio)
    params = seen["posts"][0].url.params
    assert "num_speakers" not in params
    assert params["language"] == "ar"
    assert params["diarize"] == "true"


def test_timeout(audio):
    handler, seen = scripted([202] * 100)
    client, ft = make_client(handler, poll_interval=10, poll_timeout=25)

    with pytest.raises(STTTimeoutError, match="fc-123"):
        client.transcribe(audio)
    assert ft.sleeps == [10, 10, 5]  # last sleep clipped to the deadline
    assert len(seen["gets"]) == 4
    assert ft.now == 25


def test_timeout_is_a_timeouterror():
    assert issubclass(STTTimeoutError, TimeoutError)
    assert issubclass(STTTimeoutError, STTError)


def test_transient_network_error_keeps_polling(audio):
    req = httpx.Request("GET", RESULT)
    handler, seen = scripted([202, httpx.ConnectError("down", request=req), 200])
    client, _ = make_client(handler, poll_interval=1)
    assert client.transcribe(audio) == TRANSCRIPT
    assert len(seen["gets"]) == 3


def test_job_failure_raises(audio):
    handler, _ = scripted([202, 500])
    client, _ = make_client(handler, poll_interval=1)
    with pytest.raises(STTError, match="HTTP 500"):
        client.transcribe(audio)


def test_submit_error(audio):
    client, _ = make_client(lambda r: httpx.Response(413, text="too large"))
    with pytest.raises(STTError, match="HTTP 413"):
        client.submit(audio)


def test_submit_without_call_id(audio):
    client, _ = make_client(lambda r: httpx.Response(200, json={"oops": 1}))
    with pytest.raises(STTError, match="call_id"):
        client.submit(audio)


def test_missing_file(tmp_path):
    client, _ = make_client(lambda r: httpx.Response(200))
    with pytest.raises(STTError, match="no such file"):
        client.submit(tmp_path / "nope.m4a")


def test_urls_required():
    with pytest.raises(STTError, match="MMA_STT_SUBMIT_URL"):
        ModalSTTClient(submit_url="", result_url=RESULT)


def test_from_config():
    stt = STTConfig(submit_url=SUBMIT, result_url=RESULT, language="auto", num_speakers=3,
                    poll_interval=2, poll_timeout=60)
    client = ModalSTTClient.from_config(stt, poll_interval=1)
    assert client.language == "auto"
    assert client.num_speakers == 3
    assert client.poll_interval == 1
    assert client.poll_timeout == 60


# ── large video -> local audio extraction ────────────────────────────────────
def test_should_extract_audio(tmp_path):
    small_video = tmp_path / "a.mp4"
    small_video.write_bytes(b"\x00" * 10)
    big_video = tmp_path / "b.MOV"
    big_video.write_bytes(b"\x00" * 101)
    big_audio = tmp_path / "c.wav"
    big_audio.write_bytes(b"\x00" * 101)

    assert not modal_client.should_extract_audio(small_video, 100)
    assert modal_client.should_extract_audio(big_video, 100)
    assert not modal_client.should_extract_audio(big_audio, 100)


def test_large_video_is_extracted_before_upload(tmp_path, monkeypatch):
    video = tmp_path / "meeting.mp4"
    video.write_bytes(b"\x00" * 200)
    calls = []

    def fake_extract(src, dst):
        calls.append((src, dst))
        dst.write_bytes(b"audio")
        return dst

    monkeypatch.setattr(modal_client, "extract_audio", fake_extract)
    handler, seen = scripted([200])
    client, _ = make_client(handler, max_upload_bytes=100)
    client.transcribe(video)

    assert calls and calls[0][0] == video
    body = seen["posts"][0].read()
    assert b'filename="meeting.m4a"' in body
    assert b"audio" in body
    assert not calls[0][1].exists()  # temp file cleaned up


def test_small_video_uploaded_as_is(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 50)
    monkeypatch.setattr(modal_client, "extract_audio", lambda *a: pytest.fail("extracted"))
    handler, seen = scripted([200])
    client, _ = make_client(handler, max_upload_bytes=100)
    client.transcribe(video)
    assert b'filename="clip.mp4"' in seen["posts"][0].read()


def test_ffmpeg_cmd_drops_video_and_downmixes(tmp_path):
    cmd = modal_client.ffmpeg_extract_cmd(tmp_path / "in.mp4", tmp_path / "out.m4a")
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[-1].endswith("out.m4a")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_audio_real_ffmpeg(tmp_path):
    src = tmp_path / "tiny.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", str(src)],
        check=True,
    )
    out = modal_client.extract_audio(src, tmp_path / "tiny.m4a")
    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    assert [s["codec_type"] for s in streams] == ["audio"]
    assert streams[0]["sample_rate"] == "16000"
    assert streams[0]["channels"] == 1
