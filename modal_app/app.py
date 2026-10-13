"""Serverless Arabic Whisper transcription + diarization on Modal.

Linux/GPU port of the local mlx-whisper pipeline. Same fine-tuned model
(MohamedRashad/Arabic-Whisper-CodeSwitching-Edition), but run through
faster-whisper (CTranslate2) on an NVIDIA GPU that scales to zero — you only
pay for the seconds a meeting is actually being transcribed.

Four pieces:
  1. convert_model() — one-time: HF checkpoint -> CTranslate2 weights in a Volume.
  2. transcribe()    — GPU function: faster-whisper + (optional) pyannote diarization.
  3. submit()        — HTTP POST: accept an uploaded audio file, return a call_id.
  4. result()        — HTTP GET: 202 while running, 200 + transcript JSON when done.

Usage (after `modal setup` + creating the HF secret — see modal_app/README.md):
  modal run    modal_app/app.py::convert_model   # one-time, ~3 min
  modal deploy modal_app/app.py                  # persistent URL (use this)
  modal serve  modal_app/app.py                  # dev only: temporary URL, hot reload

Deploy-time settings (env vars, read on your machine when you deploy):
  MMA_MODAL_APP_NAME   app name, part of the endpoint URLs  (default: mma-stt)
  MMA_MODAL_VOLUME     Volume for converted weights + HF cache (default: mma-whisper-models)
  MMA_MODAL_GPU        GPU type                              (default: L4)
  MMA_MODAL_HF_SECRET  Modal secret holding HF_TOKEN         (default: huggingface-secret)
"""

from __future__ import annotations  # lazy annotations: heavy types resolved at runtime only

import os
from pathlib import Path

import modal

try:  # present in the Modal image; may be absent in the local env used to deploy
    from fastapi import UploadFile
except ModuleNotFoundError:  # annotations are lazy (PEP 563), resolved in-container
    UploadFile = None

# The pure alignment helpers live next to this file so they can be unit-tested
# without modal installed. Locally they import as part of the `modal_app`
# package; in the container this file runs as a top-level module and
# alignment.py is mounted beside it (see `add_local_file` below).
try:
    from modal_app.alignment import align_segments, summarize_speakers
except ModuleNotFoundError:
    from alignment import align_segments, summarize_speakers

# ── Deploy-time configuration ────────────────────────────────────────────────
APP_NAME = os.environ.get("MMA_MODAL_APP_NAME", "mma-stt")
VOLUME_NAME = os.environ.get("MMA_MODAL_VOLUME", "mma-whisper-models")
GPU = os.environ.get("MMA_MODAL_GPU", "L4")  # T4 also fine; L4 = best price/perf
HF_SECRET_NAME = os.environ.get("MMA_MODAL_HF_SECRET", "huggingface-secret")

# ── Model / infra constants ──────────────────────────────────────────────────
HF_REPO = "MohamedRashad/Arabic-Whisper-CodeSwitching-Edition"
MODELS_DIR = "/models"                          # Volume mount point
CT2_DIR = f"{MODELS_DIR}/ct2_arabic_whisper"    # converted weights live here
DIARIZE_MODEL = "pyannote/speaker-diarization-community-1"
COMPUTE_TYPE = "float16"                          # matches the local float16 setup
HOURS = 3600

# Persistent storage for the converted model + HF cache (pyannote weights).
model_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# One image shared by every function. CTranslate2 (faster-whisper) dynamically
# links libcublas.so.12 / libcudnn.so.9, which debian_slim lacks — so we base on
# NVIDIA's CUDA 12 + cuDNN 9 runtime image. torch (pulled by pyannote) bundles its
# own CUDA libs and coexists fine on top. ffmpeg decodes any input format.
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.6.2-cudnn-runtime-ubuntu22.04", add_python="3.12"
    )
    .apt_install("ffmpeg")
    .pip_install(
        "faster-whisper>=1.1.0",
        "ctranslate2>=4.5.0",
        "transformers>=4.44",      # needed by the CT2 converter
        "pyannote.audio>=4.0.4",
        "huggingface_hub>=0.24",
        "fastapi[standard]",       # web endpoint + multipart upload parsing
    )
    .env({
        "HF_HUB_CACHE": f"{MODELS_DIR}/hf-cache",  # cache pyannote weights in the Volume
        # The container re-imports this file; pass the deploy-time settings through
        # so it rebuilds the exact same app/volume/secret references.
        "MMA_MODAL_APP_NAME": APP_NAME,
        "MMA_MODAL_VOLUME": VOLUME_NAME,
        "MMA_MODAL_GPU": GPU,
        "MMA_MODAL_HF_SECRET": HF_SECRET_NAME,
    })
    # Ship the pure helpers next to this file in the container (/root is on sys.path).
    .add_local_file(Path(__file__).with_name("alignment.py"), "/root/alignment.py")
)

app = modal.App(APP_NAME, image=image)

# HF token is only needed to download the *gated* pyannote model. Create with:
#   modal secret create huggingface-secret HF_TOKEN=hf_xxx
hf_secret = modal.Secret.from_name(HF_SECRET_NAME, required_keys=["HF_TOKEN"])


# ── 1. One-time model conversion (CPU) ───────────────────────────────────────
@app.function(volumes={MODELS_DIR: model_volume}, secrets=[hf_secret], timeout=HOURS)
def convert_model(force: bool = False) -> str:
    """Download the HF fine-tune and convert it to CTranslate2 in the Volume."""
    import subprocess

    if os.path.exists(os.path.join(CT2_DIR, "model.bin")) and not force:
        return f"Already converted at {CT2_DIR} (pass force=True to rebuild)."

    print(f"Converting {HF_REPO} -> {CT2_DIR} (quantization={COMPUTE_TYPE})...")
    # No --copy_files: this fine-tune ships the *slow* tokenizer (vocab.json +
    # merges.txt), not the single tokenizer.json that faster-whisper needs.
    subprocess.run(
        [
            "ct2-transformers-converter",
            "--model", HF_REPO,
            "--output_dir", CT2_DIR,
            "--quantization", COMPUTE_TYPE,
            "--force",
        ],
        check=True,
    )

    # faster-whisper loads tokenizer.json + preprocessor_config.json from the model
    # dir. Regenerate them with transformers (saves the *fast* tokenizer.json). The
    # large-v2 tokenizer is identical across checkpoints, so fall back to the base.
    from transformers import WhisperFeatureExtractor, WhisperTokenizerFast

    try:
        tokenizer = WhisperTokenizerFast.from_pretrained(HF_REPO)
    except Exception as exc:  # repo lacks usable tokenizer files
        print(f"Tokenizer unavailable on fine-tune ({exc}); using openai/whisper-large-v2.")
        tokenizer = WhisperTokenizerFast.from_pretrained("openai/whisper-large-v2")
    tokenizer.save_pretrained(CT2_DIR)  # writes tokenizer.json

    try:
        feature_extractor = WhisperFeatureExtractor.from_pretrained(HF_REPO)
    except Exception:
        feature_extractor = WhisperFeatureExtractor.from_pretrained("openai/whisper-large-v2")
    feature_extractor.save_pretrained(CT2_DIR)  # writes preprocessor_config.json

    model_volume.commit()  # persist weights + tokenizer
    print("Done.")
    return f"Converted -> {CT2_DIR}"


# ── 2. Transcribe + diarize (GPU) ────────────────────────────────────────────
@app.function(
    gpu=GPU,
    volumes={MODELS_DIR: model_volume},
    secrets=[hf_secret],
    timeout=2 * HOURS,
)
def transcribe(
    audio_bytes: bytes,
    filename: str = "audio",
    diarize: bool = True,
    num_speakers: int | None = None,
    language: str | None = "ar",  # None = auto-detect
) -> dict:
    """Run faster-whisper, then optional pyannote diarization, on raw audio bytes."""
    import subprocess
    import tempfile

    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, filename)
        with open(src, "wb") as f:
            f.write(audio_bytes)

        # Normalize to 16 kHz mono WAV. Sidesteps the mp3 encoder-delay priming
        # issue that breaks pyannote on raw mp3, and gives both models a clean input.
        wav = os.path.join(tmp, "audio.wav")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav],
            check=True, capture_output=True,
        )

        # --- Transcription (faster-whisper) ---
        model = WhisperModel(CT2_DIR, device="cuda", compute_type=COMPUTE_TYPE)
        seg_iter, info = model.transcribe(
            wav,
            language=language,
            task="transcribe",
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
            vad_filter=True,  # drop non-speech; pyannote VAD-equivalent
            beam_size=5,
        )
        segments = [
            {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text}
            for s in seg_iter
        ]
        text = "".join(s["text"] for s in segments).strip()

        result: dict = {
            "filename": filename,
            "language": info.language,
            "duration": round(info.duration, 2),
            "text": text,
            "segments": segments,
            "diarized": False,
        }

        if not diarize:
            return result

        # --- Diarization (pyannote) ---
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(DIARIZE_MODEL, token=os.environ["HF_TOKEN"])
        pipeline.to(torch.device("cuda"))
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        output = pipeline(wav, **kwargs)

        # exclusive_speaker_diarization: one speaker per instant (overlaps resolved),
        # which is what you want when each transcript segment gets a single label.
        turns = [
            {"start": float(turn.start), "end": float(turn.end), "speaker": str(spk)}
            for turn, _, spk in output.exclusive_speaker_diarization.itertracks(yield_label=True)
        ]
        turns.sort(key=lambda t: t["start"])

        aligned = align_segments(segments, turns, fill_nearest=False)
        result["segments"] = aligned
        result["speakers"] = summarize_speakers(aligned)
        result["diarized"] = True

        model_volume.commit()  # persist pyannote weights cached on first run
        return result


# ── 3. HTTP endpoints (CPU) — upload audio, poll for JSON ────────────────────
# Modal web requests must respond within 150s, but a full meeting takes longer.
# So `submit` only *spawns* the GPU job and returns a call_id instantly; `result`
# fetches the transcript once it's ready (the standard Modal job-queue pattern).
@app.function()
@modal.fastapi_endpoint(method="POST", docs=True)
async def submit(
    file: UploadFile,
    language: str = "ar",
    diarize: bool = True,
    num_speakers: int | None = None,
):
    """POST audio as multipart field `file`; returns {"call_id"} immediately.

    Query params:
      language      "ar" (default), "en", ... or "auto" to detect.
      diarize       "true" (default) / "false" to skip pyannote.
      num_speakers  exact speaker count if known; omit to let pyannote estimate.

    Test:  curl -F file=@meeting.m4a "<submit-url>?language=en&num_speakers=4"
           # -> {"call_id": "fc-..."}
           curl "<result-url>?call_id=fc-..."   # poll: 202 while running, 200 when done
    """
    audio_bytes = await file.read()
    call = await transcribe.spawn.aio(
        audio_bytes,
        # basename: the client-supplied name becomes a path inside the container
        filename=os.path.basename(file.filename or "") or "audio",
        diarize=diarize,
        num_speakers=num_speakers,
        language=None if language == "auto" else language,
    )
    return {"call_id": call.object_id}


@app.function()
@modal.fastapi_endpoint(method="GET", docs=True)
async def result(call_id: str):
    """GET ?call_id=<id> -> 200 with the transcript JSON, or 202 while still running."""
    from fastapi.responses import JSONResponse

    function_call = modal.FunctionCall.from_id(call_id)
    try:
        return await function_call.get.aio(timeout=0)
    except TimeoutError:
        return JSONResponse({"status": "processing"}, status_code=202)
