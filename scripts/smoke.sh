#!/usr/bin/env bash
# Offline smoke test: no Modal, no GPU, no network, no agent.
# Renders the synthetic sample transcript, validates the sample brief JSON and
# installs the skill into a temp folder. Run from the repo root:
#   bash scripts/smoke.sh
set -euo pipefail

cd "$(dirname "$0")/.."
if command -v uv >/dev/null 2>&1; then MMA=(uv run mma); else MMA=(mma); fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "== mma doctor"
"${MMA[@]}" doctor

echo "== mma transcript (sample meeting)"
"${MMA[@]}" transcript examples/sample-meeting/demo.json \
  --names "SPEAKER_00=Layla,SPEAKER_01=Omar" --out "$tmp/results"
for f in demo.json demo.clean.md demo.transcript.html; do
  test -s "$tmp/results/$f" || { echo "missing $f"; exit 1; }
done
turns=$(grep -c '^\[' "$tmp/results/demo.clean.md")
test "$turns" -eq 22 || { echo "expected 22 merged turns, got $turns"; exit 1; }
grep -q '^\[00:00\] Layla: ' "$tmp/results/demo.clean.md"
head -n 6 "$tmp/results/demo.clean.md"

echo "== mma validate (sample brief JSON)"
"${MMA[@]}" validate examples/sample-meeting/expected/demo.actions.json

echo "== mma skill install (temp folder)"
"${MMA[@]}" skill install --dest "$tmp/skills"
"${MMA[@]}" skill install --dest "$tmp/skills" | grep -q 'up to date'
test -f "$tmp/skills/process-meeting/SKILL.md"

echo "OK: offline smoke test passed"
