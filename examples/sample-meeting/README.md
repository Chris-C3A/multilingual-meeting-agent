# Sample meeting (synthetic)

A fictional, ~3-minute product sync between **Layla** (Levantine Arabic) and
**Omar** (Gulf Arabic), switching to English mid-sentence the way real
meetings do. Everything here is made up: the people, the client, the numbers.
There is no audio file; the transcript was written by hand.

| File | What |
|---|---|
| `demo.json` | Transcript in the exact shape the Modal app returns (`filename`, `language`, `duration`, `text`, `segments[start,end,text,speaker]`, `speakers[]`, `diarized`). `SPEAKER_00` = Layla, `SPEAKER_01` = Omar, one `UNKNOWN` segment. |
| `expected/demo.actions.json` | A hand-written reference of what `/process-meeting` should extract. Valid against `skills/process-meeting/templates/brief.schema.json`. Not an agent run's output; your agent's wording will differ. |

What's in it: two decisions (daily batch job for points expiry; push
notifications only, SMS parked), three dated action items (API docs Thursday,
Arabic copy Tuesday, staging deploy Sunday), two open questions (which two
branches, SMS budget) and a mentioned-but-absent designer, Rana.

## Follow along (no Modal, no GPU)

From the repo root:

```bash
uv run mma transcript examples/sample-meeting/demo.json \
  --names "SPEAKER_00=Layla,SPEAKER_01=Omar"
# -> results/demo.json, results/demo.clean.md, results/demo.transcript.html

uv run mma skill install            # Claude Code; --target opencode|hermes|all
```

Then, in your agent, from the repo root:

```
/process-meeting demo
```

You should get `results/demo.actions.json`, `results/demo.brief.md`,
`results/demo.brief.html` and the marker `results/demo.processed.json`.
Compare with `expected/demo.actions.json`, and check the JSON with
`uv run mma validate results/demo.actions.json`.

Merging rule worth noticing in `results/demo.clean.md`: Layla's first two
segments (0.4 s apart) become one turn at `[00:00]`; Omar's turns at `[02:03]`
and `[02:26]` stay separate because 17.5 s of silence sits between them
(merge threshold: < 15 s).

Real recordings need the deployed Modal app; see
[`modal_app/README.md`](../../modal_app/README.md) and `mma run`.
