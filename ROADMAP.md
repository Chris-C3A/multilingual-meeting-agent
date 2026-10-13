# Roadmap

Each phase lands as its own PR, built by Claude Code (Opus 5.5) and independently verified before merge.

## Phase 0: Foundation
- [x] Repo hygiene: LICENSE (MIT), `.gitignore`, `pyproject.toml` (uv), ruff, pytest
- [x] `config.example.yaml` + env var conventions (`MMA_*`, `HF_TOKEN`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SMTP_*`, `SLACK_WEBHOOK_URL`)
- [x] `docs/architecture.md` with the pipeline diagram
- [x] CI: lint + tests on push/PR

## Phase 1: Modal transcription app
- [x] `modal_app/app.py`: faster-whisper + code-switching fine-tune on L4, float16, beam 5, VAD
- [x] pyannote diarization, speaker-to-segment alignment
- [x] Async API: `POST /submit` → call id, `GET /result` (202 running / 200 done)
- [x] `modal deploy` instructions (stable URL, not `modal serve`)
- [x] Handles missing `tokenizer.json` in the fine-tune repo

## Phase 2: Core pipeline + CLI
- [x] `mma run <audio>`: submit → poll → write `<stem>.json`, `<stem>.clean.md` (merged speaker turns, timestamps), `<stem>.transcript.html` (tested with a fake client; not yet run against a real deployment)
- [x] Speaker naming (`--names SPEAKER_00=Chris,...`), re-render offline with `mma transcript`
- [ ] Sources: watched folder (default), PLAUD cloud (optional plugin)
- [ ] Idempotency: completion markers, never process a recording twice (partial: `mma run` skips existing outputs; the skill writes `<stem>.processed.json`)

## Phase 3: Agent layer + skills
- [x] `skills/process-meeting/SKILL.md`: brief structure, action items, decisions, people/companies, language notes
- [x] Brief JSON schema the agent must fill; validated before sinks run (`mma validate`)
- [ ] Runner: Claude Code primary, OpenCode fallback, per-recording override
- [ ] Hermes skill wrapper (`mma skill install --target hermes` copies the skill; not tested inside Hermes)

## Phase 4: Sinks + rules
- [ ] Brief (Markdown + HTML template) (template + skill instructions done; no code renderer)
- [ ] GitHub issues from action items
- [ ] Email (SMTP), Slack (webhook), markdown wiki folder
- [ ] Rules: privacy mode (owner-only), per-recipient routing

## Phase 5: Demo kit
- [x] Synthetic code-switched sample meeting (Arabic dialects + English), no real data
- [ ] `make demo`: end-to-end in under ~5 minutes (offline part: `bash scripts/smoke.sh`)
- [ ] Dockerfile
- [ ] README walkthrough + screenshots/GIF (walkthrough: `AGENT_SETUP.md`; no screenshots yet)

## Agent install
- [x] `AGENT_SETUP.md`: one copy-paste prompt for coding agents, with checkpoints and stop-and-ask points
- [x] `mma doctor`, `mma skill install`, `mma transcript`, `mma validate`

## Phase 6: Launch
- [ ] Tests green, docs complete, secrets scan clean
- [ ] Make repo public
- [ ] Link from the talk
