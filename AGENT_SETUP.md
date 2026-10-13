# Install with your AI coding agent

Copy the block below into Claude Code, Codex, OpenCode, Hermes or any coding
agent that can run shell commands. It clones the repo, installs it, runs an
offline test with a synthetic meeting, installs the `process-meeting` skill,
and (only if you say yes) sets up real transcription on your own Modal
account. The agent stops and asks you at every login, terms page, token and
spending decision.

````text
You are setting up github.com/Chris-C3A/multilingual-meeting-agent for me:
a pipeline that transcribes code-switched Arabic/English meetings on a Modal
GPU and turns them into briefs with an agent skill. Follow these steps in
order. After each step, check the CHECKPOINT; if it fails, stop and tell me
what failed (the exact output) instead of improvising a workaround.

RULES
- Lines marked STOP: stop, explain in one or two sentences what is needed and
  why, and wait for my answer.
- Never log in, accept terms, create tokens or spend money for me.
- Never print, store, commit or echo secrets (tokens, keys). Never commit
  config.yaml, results/ or recordings.
- Don't run any outbound sink (GitHub issues, email, Slack, wiki) unless I ask.
- Use `uv run mma ...` for every mma command (or plain `mma ...` if you used
  the pip fallback in step 2 and the venv is active).

1. CLONE
   If the current folder is not already this repo:
     git clone https://github.com/Chris-C3A/multilingual-meeting-agent.git
     cd multilingual-meeting-agent
   CHECKPOINT: AGENT_SETUP.md and pyproject.toml exist in the current folder.

2. INSTALL (Python >= 3.11)
   If `uv` is on PATH:
     uv sync
   If not: STOP and ask whether to install uv
   (https://docs.astral.sh/uv/getting-started/installation/) or use pip. pip
   fallback:
     python3 -m venv .venv && . .venv/bin/activate && pip install -e . pytest ruff
   CHECKPOINT: `uv run mma --version` prints "mma 0.1.0".

3. DOCTOR
     uv run mma doctor
   CHECKPOINT: exit code 0 and no ❌ lines. ⚠️ lines for modal token, HF_TOKEN,
   MMA_STT_SUBMIT_URL/RESULT_URL and "skill installed" are expected at this
   point. ❌ means a hard requirement is missing (e.g. Python too old): STOP.

4. OFFLINE SMOKE TEST (no Modal, no GPU, no network)
     bash scripts/smoke.sh
     uv run pytest -q
   CHECKPOINT: the script ends with "OK: offline smoke test passed" and pytest
   reports no failures. (On Windows without bash, skip the script and rely on
   pytest plus step 5.)

5. RENDER THE SAMPLE MEETING
     uv run mma transcript examples/sample-meeting/demo.json --names "SPEAKER_00=Layla,SPEAKER_01=Omar"
   CHECKPOINT: results/demo.json, results/demo.clean.md and
   results/demo.transcript.html exist; results/demo.clean.md has lines like
   "[00:00] Layla: صباح الخير عمر، shall we start? ...".

6. INSTALL THE SKILL for the agent you are:
     uv run mma skill install --target claude      # Claude Code
     uv run mma skill install --target opencode    # OpenCode
     uv run mma skill install --target hermes      # Hermes
     uv run mma skill install --dest <skills dir>  # any other agent: its skills folder
   If your agent has no skills folder, skip installing and in step 7 read
   skills/process-meeting/SKILL.md and follow it directly.
   CHECKPOINT: `uv run mma doctor` shows "✅ skill installed" (for the three
   named targets; --dest installs aren't checked by doctor).

7. RUN THE SKILL ON THE SAMPLE
   Run `/process-meeting demo` from the repo root. Skills are often loaded only
   at session start: if the command isn't available, read
   skills/process-meeting/SKILL.md and follow it for stem "demo" yourself, and
   tell me a new session will pick up the slash command.
   CHECKPOINT: results/demo.actions.json, results/demo.brief.md,
   results/demo.brief.html and results/demo.processed.json exist, and
     uv run mma validate results/demo.actions.json
   prints ✅. Compare with examples/sample-meeting/expected/demo.actions.json:
   it should find the same decisions (daily expiry job; push only, SMS parked)
   and action items (API docs Thursday, Arabic copy Tuesday, staging Sunday).

   STOP: report steps 1-7 to me, then ask whether I want real transcription.
   It needs a Modal account (my login), a Hugging Face account (my login +
   accepting model terms), and costs GPU time on my Modal bill (the README's
   reference is ~$1-3/month for daily meetings on an L4; the app scales to
   zero when idle). If I say no, jump to REPORT BACK.

8. MODAL SETUP (only if I said yes)
   a. Install the Modal client and log in:
        uv sync --group modal
        uv run modal setup
      STOP: `modal setup` opens a browser; I complete the login.
      CHECKPOINT: `uv run mma doctor` shows "✅ modal token" (presence only).
   b. STOP: ask me to (1) open
      https://huggingface.co/pyannote/speaker-diarization-community-1 while
      signed in and accept its conditions, and (2) create a read token at
      https://huggingface.co/settings/tokens.
   c. Store the token in Modal. Ask me to run this myself in a terminal, so
      the token never passes through you (in Claude Code I can type it after
      a leading "!"):
        uv run modal secret create huggingface-secret HF_TOKEN=<my token>
      If I paste the token to you instead, use it only in that one command;
      don't repeat it, save it or put it in any file.
      CHECKPOINT: `uv run modal secret list` shows huggingface-secret.
   d. STOP: confirm I'm OK spending Modal credits, then:
        uv run modal run modal_app/app.py::convert_model
      (one-time, ~3 min, CPU; downloads the GPL-3.0 model into my Modal
      Volume, never into this repo)
        uv run modal deploy modal_app/app.py
      Use deploy, not `modal serve`. CHECKPOINT: deploy prints two URLs ending
      in -submit.modal.run and -result.modal.run.
   e. Point mma at them. Either export them in my shell profile:
        export MMA_STT_SUBMIT_URL=<submit url>
        export MMA_STT_RESULT_URL=<result url>
      or `cp config.example.yaml config.yaml` and set stt.submit_url and
      stt.result_url (config.yaml is git-ignored).
      CHECKPOINT: `uv run mma doctor` shows ✅ for both URLs.
   f. STOP: ask me for a short real recording (1-3 minutes, audio or video)
      and my OK to upload it to my Modal app. Ask which language: ar (default,
      code-switched Arabic/English), en (English only; the Arabic model may
      translate English if forced to ar) or auto. Then:
        uv run mma run <path> --language ar --num-speakers <N if known>
      The first call cold-starts the GPU and caches the diarization model, so
      it can take a few minutes. Re-running skips existing outputs unless you
      add --force.
      CHECKPOINT: results/<stem>.json, .clean.md and .transcript.html exist and
      clean.md reads like the meeting.
   g. Read results/<stem>.clean.md, propose who SPEAKER_00, SPEAKER_01, ...
      are, STOP for my confirmation, then:
        uv run mma transcript results/<stem>.json --names "SPEAKER_00=<name>,SPEAKER_01=<name>"
   h. Run `/process-meeting <stem>`. CHECKPOINT as in step 7.

REPORT BACK: finish by printing this checklist for me, each line ✅, ⚠️ or ❌
with a short note:
  [ ] repo cloned at <path>, installed with uv / pip
  [ ] mma doctor: hard requirements OK (list any ⚠️)
  [ ] offline smoke test + pytest passed
  [ ] sample rendered: results/demo.clean.md
  [ ] skill installed for <agent> at <path>
  [ ] /process-meeting demo produced brief.md / brief.html / actions.json (validated)
  [ ] Modal: logged in / HF terms + secret / model converted / deployed / URLs set (or "skipped")
  [ ] real recording transcribed: results/<stem>.* (or "skipped")
  [ ] anything I still need to do myself
````

## Manual quick start (no agent)

```bash
git clone https://github.com/Chris-C3A/multilingual-meeting-agent.git
cd multilingual-meeting-agent
uv sync
uv run mma doctor
bash scripts/smoke.sh                     # offline: sample transcript, schema, skill copy

# Sample meeting, no Modal needed
uv run mma transcript examples/sample-meeting/demo.json \
  --names "SPEAKER_00=Layla,SPEAKER_01=Omar"
uv run mma skill install                  # --target opencode | hermes | all, or --dest DIR
# then in Claude Code, from the repo root:  /process-meeting demo

# Real recordings: deploy the Modal app (see modal_app/README.md)
uv sync --group modal
uv run modal setup
# accept https://huggingface.co/pyannote/speaker-diarization-community-1, make a read token
uv run modal secret create huggingface-secret HF_TOKEN=hf_xxx
uv run modal run modal_app/app.py::convert_model
uv run modal deploy modal_app/app.py
export MMA_STT_SUBMIT_URL=https://<workspace>--mma-stt-submit.modal.run
export MMA_STT_RESULT_URL=https://<workspace>--mma-stt-result.modal.run
uv run mma run meeting.m4a --language ar --num-speakers 2
uv run mma transcript results/meeting.json --names "SPEAKER_00=Alice,SPEAKER_01=Bob"
# then: /process-meeting meeting
```

## Commands

| Command | What |
|---|---|
| `mma run <audio> [--language ar\|en\|auto] [--names ...] [--num-speakers N] [--out results/] [--force]` | Transcribe on the deployed Modal app; writes `<stem>.json`, `<stem>.clean.md`, `<stem>.transcript.html`. Skips if all three exist. |
| `mma transcript <stem.json> [--names ...] [--out results/]` | Re-render clean.md + HTML from a JSON, offline. Stores names in the JSON. |
| `mma doctor` | Local checks (Python, config, ffmpeg, Modal CLI/token, HF_TOKEN, STT URLs, agent CLIs, skill). Exit 1 only on a hard failure. |
| `mma skill install [--target claude\|opencode\|hermes\|all] [--dest DIR]` | Copy `skills/process-meeting/` to `~/.claude/skills/`, `~/.config/opencode/skills/` (honours `XDG_CONFIG_HOME`), `~/.hermes/skills/`, or `DIR`. Idempotent. |
| `mma validate <stem.actions.json>` | Check the agent's structured brief against `brief.schema.json`. |

## What's verified and what isn't

- Verified by the test suite and `scripts/smoke.sh` (offline): every `mma`
  command above, the sample transcript rendering and merge rule, the schema,
  and skill copying (with a fake home folder). `mma run` is tested against a
  fake STT client only.
- Checked by reading the tools, not by running a skill in them: OpenCode
  1.18 globs `{skill,skills}/**/SKILL.md` under `~/.config/opencode/`; Hermes
  finds `SKILL.md` files recursively under `~/.hermes/skills/`. Whether each
  exposes it as `/process-meeting` is not verified.
- **Not verified in this repo's CI:** the agent actually running
  `/process-meeting` (that needs an agent and an LLM), the Modal steps, `mma
  run` against a real deployment, Codex (no standard skills folder assumed;
  use `--dest` or point it at `SKILL.md`), and the optional sinks.
