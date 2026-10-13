# multilingual-meeting-agent

**From Voice to Action, Beyond English: a custom meeting agent for code-switched Arabic and English.**

Record anywhere, transcribe mixed Arabic dialects + English, and let an agent turn the meeting into a brief, tasks and follow-ups.

> 🚧 Work in progress. This repo is an open-source mimic of a production pipeline used daily in Qatar, built in public.

## Why

Most meeting AI (including the AI built into consumer recorders) works well only in English. Real meetings in the Gulf switch between Arabic dialects and English mid-sentence, and off-the-shelf transcripts fall apart. This project keeps the hardware, replaces the brain, and owns every step:

```
recorder (e.g. PLAUD) / audio folder
        │
        ▼
 Modal GPU (L4, scale-to-zero)
   faster-whisper + Arabic–English code-switching fine-tune
   pyannote speaker diarization
        │  transcript.json / clean.md
        ▼
 Agent (Claude Code, OpenCode fallback) driven by skill files
        │
        ▼
 brief (HTML/MD) · GitHub issues · email · Slack · markdown wiki
```

## Stack

| Layer | Choice |
|---|---|
| Transcription model | [`MohamedRashad/Arabic-Whisper-CodeSwitching-Edition`](https://huggingface.co/MohamedRashad/Arabic-Whisper-CodeSwitching-Edition) (Whisper large-v2 fine-tune, GPL-3.0, downloaded at runtime, not redistributed) |
| Inference | faster-whisper / CTranslate2, float16, beam 5, VAD filter |
| Diarization | pyannote `speaker-diarization-community-1` (needs `HF_TOKEN`) |
| Compute | [Modal](https://modal.com) L4 GPU, scale-to-zero; async `POST /submit` + `GET /result` to avoid the 150 s web limit |
| Agent | Claude Code with skill files (`skills/`), OpenCode fallback |
| Outputs | Markdown/HTML brief, GitHub issues, SMTP email, Slack webhook, markdown wiki |

Reference numbers from the production pipeline: a 22-minute meeting with 4 speakers transcribes in ~3.4 min (~6.5× realtime) for roughly $1–3/month.

## Planned layout

```
modal_app/        Modal STT app (one-command deploy)
mma/              Python package + CLI (`mma run <audio>`)
  sources/        folder watcher, PLAUD (optional)
  stt/            Modal client
  agent/          Claude Code / OpenCode runners
  sinks/          brief, github, email, slack, wiki
  rules.py        privacy modes, routing, idempotency
skills/           agent skill files (Claude Code + Hermes)
examples/         synthetic code-switched sample meeting + config
docs/             architecture, talk notes
```

See [ROADMAP.md](ROADMAP.md) for the build plan.

## License

MIT for this repository's code. The transcription model is GPL-3.0 and is fetched at runtime from Hugging Face; its weights are not included here.
