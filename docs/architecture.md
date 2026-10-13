# Architecture

## Why this exists: code-switching

Meetings in the Gulf rarely stay in one language. A speaker starts a sentence in
Gulf or Levantine Arabic, drops into English for a technical term or a whole
clause, and switches back, sometimes several times a minute. Off-the-shelf
meeting AI (including the transcription built into consumer recorders) is tuned
for monolingual English. On code-switched audio it either translates everything
into one language, hallucinates, or drops the English islands entirely, and
every step downstream (summary, action items, owners) inherits those errors.

So the pipeline keeps the cheap, convenient parts (any recorder, any audio
folder) and replaces the brain: a Whisper fine-tune trained on Arabic/English
code-switching, speaker diarization, and an agent that reads the result the way
a bilingual colleague would.

## Pipeline

```
 ┌──────────────────────────────┐
 │ Sources                      │  watched folder (default), PLAUD cloud (optional)
 │   mma/sources/               │  -> local audio/video file
 └──────────────┬───────────────┘
                │ audio file (video: audio extracted locally with ffmpeg)
                ▼
 ┌──────────────────────────────┐
 │ STT client                   │  POST file -> /submit  => {"call_id"}
 │   mma/stt/                   │  GET /result?call_id=  => 202 running / 200 done
 └──────────────┬───────────────┘
                │ HTTPS
                ▼
 ┌──────────────────────────────┐
 │ Modal app (GPU, L4)          │  ffmpeg -> 16 kHz mono WAV
 │   modal_app/                 │  faster-whisper (CT2, float16, beam 5, VAD)
 │   scale-to-zero              │  pyannote community-1 diarization
 │                              │  segment <-> speaker alignment
 └──────────────┬───────────────┘
                │ transcript.json
                ▼
 ┌──────────────────────────────┐
 │ Core pipeline                │  transcript.json, clean.md (merged speaker turns),
 │   mma/ (CLI: mma run)        │  transcript.html, speaker naming, idempotency
 └──────────────┬───────────────┘
                │ clean.md + skill files
                ▼
 ┌──────────────────────────────┐
 │ Agent layer                  │  Claude Code (primary), OpenCode (fallback)
 │   mma/agent/, skills/        │  fills a brief JSON schema; validated before sinks
 └──────────────┬───────────────┘
                │ brief.json
                ▼
 ┌──────────────────────────────┐
 │ Rules + sinks                │  privacy mode, per-recipient routing
 │   mma/rules.py, mma/sinks/   │  brief (MD/HTML), GitHub issues, email, Slack, wiki
 └──────────────────────────────┘
```

## Layer responsibilities

| Layer | Owns | Does not own |
|---|---|---|
| **Sources** (`mma/sources/`) | Discovering new recordings and handing a local file path to the pipeline. | Any processing of the audio. |
| **STT client** (`mma/stt/`) | Uploading audio to the Modal `submit` endpoint, polling `result` (202 = still running, 200 = done), timeouts, shrinking large video to audio before upload. | Model choice, GPU, diarization. |
| **Modal app** (`modal_app/`) | One-time model conversion to CTranslate2, GPU transcription, diarization, speaker alignment, the async HTTP API. Scales to zero between meetings. | Anything after the transcript. |
| **Core pipeline** (`mma/`, `mma run`) | Orchestration, output files, speaker naming, completion markers so a recording is never processed twice. | Interpreting meeting content. |
| **Agent layer** (`mma/agent/`, `skills/`) | Turning the transcript into a structured brief: summary, decisions, action items with owners, people/companies, language notes. | Delivering anything. |
| **Rules + sinks** (`mma/rules.py`, `mma/sinks/`) | Who may see what (privacy mode), routing, and delivery to each destination. | Producing content. |

## Why an async API on Modal

Modal web endpoints must respond within 150 seconds; a real meeting takes
minutes to transcribe. The `submit` endpoint therefore only *spawns* the GPU
job and returns a `call_id` immediately; `result` returns HTTP 202 while the job
runs and HTTP 200 with the transcript once it finishes. The client just polls.

## Configuration

One YAML file (`config.example.yaml` documents every key) plus environment
variables. Env vars override the file; secrets (`HF_TOKEN`,
`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SMTP_PASSWORD`, `SLACK_WEBHOOK_URL`) are
read from the environment only. See `mma/config.py`.

## Licensing boundary

This repository is MIT. The transcription model
(`MohamedRashad/Arabic-Whisper-CodeSwitching-Edition`) is GPL-3.0 and is
downloaded from Hugging Face at runtime inside the Modal container; its weights
are never stored in or distributed with this repository.
