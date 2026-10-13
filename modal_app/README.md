# Modal STT app

Serverless transcription + speaker diarization for code-switched Arabic/English
meetings, on a Modal GPU that scales to zero.

- **Model:** [`MohamedRashad/Arabic-Whisper-CodeSwitching-Edition`](https://huggingface.co/MohamedRashad/Arabic-Whisper-CodeSwitching-Edition)
  (Whisper large-v2 fine-tune), converted once to CTranslate2 and run with
  faster-whisper (float16, beam 5, VAD filter).
- **Diarization:** [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1),
  exclusive (one speaker at a time) turns aligned to Whisper segments.
- **API:** `POST submit` returns a `call_id` immediately; `GET result` answers
  `202` while the job runs and `200` with the transcript when it's done. Modal
  web requests must finish within 150 s, and a meeting takes minutes, so the
  endpoint never waits on the GPU.

Files:

| File | What |
|---|---|
| `app.py` | The Modal app: image, `convert_model`, `transcribe`, `submit`, `result`. |
| `alignment.py` | Pure helpers (segment/speaker alignment, talk-time summary). No Modal needed; unit-tested in `tests/`. |

## 1. Install and authenticate Modal

```bash
uv sync --group modal          # or: pip install modal
uv run modal setup             # opens a browser, stores a token in ~/.modal.toml
```

## 2. Accept the pyannote model terms

`pyannote/speaker-diarization-community-1` is a gated model. Signed in to
Hugging Face, open its model page and accept the conditions. Then create a
read token at <https://huggingface.co/settings/tokens>.

## 3. Store the token as a Modal secret

```bash
modal secret create huggingface-secret HF_TOKEN=hf_xxx
```

The token lives in Modal, never in this repo. (Use a different secret name by
setting `MMA_MODAL_HF_SECRET` when you run/deploy.)

## 4. Convert the model (one-time, ~3 min)

```bash
modal run modal_app/app.py::convert_model
```

This downloads the fine-tune from Hugging Face, converts it to CTranslate2
float16 into a Modal Volume (`mma-whisper-models`), and writes the
`tokenizer.json` / `preprocessor_config.json` that faster-whisper needs. The
fine-tune ships only the *slow* tokenizer files, so they are regenerated with
`transformers`, falling back to `openai/whisper-large-v2` (same tokenizer) if
the fine-tune's files can't be loaded. Re-run with `--force` to rebuild.

## 5. Deploy

```bash
modal deploy modal_app/app.py
```

**Use `deploy`, not `serve`.** `modal serve` gives a temporary dev URL that
disappears when you stop it (and changes between runs); `modal deploy` gives
stable URLs that keep working while scaled to zero. Deploy prints two
endpoints, shaped like:

```
https://<workspace>--mma-stt-submit.modal.run
https://<workspace>--mma-stt-result.modal.run
```

Put them in `config.yaml` (`stt.submit_url`, `stt.result_url`) or export
`MMA_STT_SUBMIT_URL` / `MMA_STT_RESULT_URL`.

### Deploy-time settings

Read from your shell when you run `modal run` / `modal deploy`:

| Env var | Default | |
|---|---|---|
| `MMA_MODAL_APP_NAME` | `mma-stt` | App name; part of the endpoint URLs. |
| `MMA_MODAL_VOLUME` | `mma-whisper-models` | Volume for converted weights + HF cache. |
| `MMA_MODAL_GPU` | `L4` | Any Modal GPU type (`T4` works too). |
| `MMA_MODAL_HF_SECRET` | `huggingface-secret` | Modal secret containing `HF_TOKEN`. |

Use the same values for `convert_model` and `deploy` so both see the same Volume.

## 6. Try it with curl

```bash
SUBMIT=https://<workspace>--mma-stt-submit.modal.run
RESULT=https://<workspace>--mma-stt-result.modal.run

# Submit (multipart field "file"). Optional query params:
#   language=ar (default) | en | ... | auto
#   diarize=true (default) | false
#   num_speakers=4          (omit to let pyannote estimate)
curl -s -F file=@meeting.m4a "$SUBMIT?language=ar&num_speakers=4"
# {"call_id":"fc-..."}

# Poll: HTTP 202 {"status":"processing"} until done, then HTTP 200 + transcript
curl -s -w '\n%{http_code}\n' "$RESULT?call_id=fc-..."
```

Or from Python: `mma.stt.ModalSTTClient` does the upload, polling, timeout,
and (for large video files) local audio extraction for you.

Response (200):

```json
{
  "filename": "meeting.m4a",
  "language": "ar",
  "duration": 1320.5,
  "text": "...",
  "segments": [{"start": 0.0, "end": 4.2, "text": "...", "speaker": "SPEAKER_00"}],
  "diarized": true,
  "speakers": [{"speaker": "SPEAKER_00", "total_seconds": 512.3, "segment_count": 140}]
}
```

Segments that overlap no diarization turn get `"speaker": "UNKNOWN"`.
Interactive API docs are served at `<submit-url>/docs`.

## Cost and performance

- **GPU:** NVIDIA L4, scale-to-zero: you pay only while a meeting is being
  transcribed; idle costs nothing.
- **Speed:** ~6.5× realtime. Reference: a 22-minute, 4-speaker meeting
  transcribes and diarizes in ~3.4 minutes.
- **Cost:** roughly $1–3/month for a typical load of daily meetings.
- **Cold start:** the first request after idle loads the model from the Volume;
  the first diarized run also caches the pyannote weights in the Volume.

## Licensing

This repository is MIT. The transcription model is **GPL-3.0**. Its weights are
downloaded from Hugging Face at runtime by `convert_model` and live only in
your Modal Volume; they are never committed to or distributed with this repo.
The pyannote model has its own terms, which you accept on Hugging Face (step 2).
