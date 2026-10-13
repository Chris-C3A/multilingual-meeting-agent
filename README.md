# multilingual-meeting-agent

**From Voice to Action, Beyond English: a custom meeting agent for code-switched Arabic and English.**

Record anywhere, transcribe mixed Arabic dialects + English, and let an agent turn the meeting into a brief, tasks and follow-ups.

> 🚧 Work in progress. This repo is an open-source mimic of a production pipeline used daily in Qatar, built in public.

## ⚡ Install with your agent

Paste this into Claude Code, Codex, OpenCode or Hermes and it will clone, install, run an offline test, install the skill and (only with your OK) deploy the Modal app:

```text
Read AGENT_SETUP.md in github.com/Chris-C3A/multilingual-meeting-agent and follow it step by step. Stop and ask me before any login, terms acceptance, token, or anything that costs money.
```

The full prompt, with checkpoints and a manual quick start, is in [AGENT_SETUP.md](AGENT_SETUP.md). No GPU? The offline path uses a synthetic sample meeting: [`examples/sample-meeting/`](examples/sample-meeting/).

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

## Layout

```
modal_app/          Modal STT app: faster-whisper + pyannote, async submit/result API
mma/                Python package + CLI
  cli.py            mma run | transcript | doctor | validate | skill install
  transcript.py     clean.md / transcript.html rendering, speaker names, turn merging
  stt/              Modal client (upload, polling, large-video audio extraction)
  doctor.py         local environment checks
  skills.py         skill installer (Claude Code, OpenCode, Hermes)
  brief.py          actions.json schema validation
  config.py         YAML + env config
skills/
  process-meeting/  agent skill: SKILL.md + brief HTML template + JSON schema
examples/
  sample-meeting/   synthetic code-switched transcript (no audio) + reference brief JSON
scripts/smoke.sh    offline smoke test
docs/               architecture
AGENT_SETUP.md      copy-paste install prompt for coding agents
```

Not built yet: folder watcher / PLAUD sources, an agent runner (`mma` doesn't launch the agent for you), and sinks as code; the skill describes the optional sinks for the agent to run with your approval.

See [ROADMAP.md](ROADMAP.md) for the build plan.

## License

MIT for this repository's code. The transcription model is GPL-3.0 and is fetched at runtime from Hugging Face; its weights are not included here.
