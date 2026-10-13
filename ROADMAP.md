# Roadmap

Each phase lands as its own PR, built by Claude Code (Opus 5.5) and independently verified before merge.

## Phase 0: Foundation
- [x] Repo hygiene: LICENSE (MIT), `.gitignore`, `pyproject.toml` (uv), ruff, pytest
- [x] `config.example.yaml` + env var conventions (`MMA_*`, `HF_TOKEN`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SMTP_*`, `SLACK_WEBHOOK_URL`)
- [x] `docs/architecture.md` with the pipeline diagram
- [x] CI: lint + tests on push/PR

## Phase 1: Modal transcription app
- [ ] `modal_app/app.py`: faster-whisper + code-switching fine-tune on L4, float16, beam 5, VAD
- [ ] pyannote diarization, speaker-to-segment alignment
- [ ] Async API: `POST /submit` → call id, `GET /result` (202 running / 200 done)
- [ ] `modal deploy` instructions (stable URL, not `modal serve`)
- [ ] Handles missing `tokenizer.json` in the fine-tune repo

## Phase 2: Core pipeline + CLI
- [ ] `mma run <audio>`: submit → poll → write `transcript.json`, `clean.md` (merged speaker turns, timestamps), `transcript.html`
- [ ] Speaker naming (`--names SPEAKER_00=Chris,...`)
- [ ] Sources: watched folder (default), PLAUD cloud (optional plugin)
- [ ] Idempotency: completion markers, never process a recording twice

## Phase 3: Agent layer + skills
- [ ] `skills/process-meeting/SKILL.md`: brief structure, action items, decisions, people/companies, language notes
- [ ] Brief JSON schema the agent must fill; validated before sinks run
- [ ] Runner: Claude Code primary, OpenCode fallback, per-recording override
- [ ] Hermes skill wrapper

## Phase 4: Sinks + rules
- [ ] Brief (Markdown + HTML template)
- [ ] GitHub issues from action items
- [ ] Email (SMTP), Slack (webhook), markdown wiki folder
- [ ] Rules: privacy mode (owner-only), per-recipient routing

## Phase 5: Demo kit
- [ ] Synthetic code-switched sample meeting (Arabic dialects + English), no real data
- [ ] `make demo`: end-to-end in under ~5 minutes
- [ ] Dockerfile
- [ ] README walkthrough + screenshots/GIF

## Phase 6: Launch
- [ ] Tests green, docs complete, secrets scan clean
- [ ] Make repo public
- [ ] Link from the talk
