# tallystone

> Portable, verifiable, decision-aware context handoffs for AI agents.

## What it is

When work moves between agents (ChatGPT → Claude → Codex → OpenCode → ...), a
chat summary loses the things that actually matter: *why* a decision was made,
*what evidence* it rests on, and *how it changed*. `tallystone` is a small,
dependency-free core for carrying that across the handoff:

- **Decisions** with rationale and rejected alternatives
- **Constraints** (non-negotiable rules/preferences) with severity
- **Change history** — which decision replaced which, and why (supersession)
- **Evidence** locators (file / commit / test / url) as provenance
- **Working state** — active task, blockers, next action
- **Budget-aware packaging** — trim a package to a token budget

It is **local-first and stdlib-only**: no network, no API keys, no servers, no
database. State is plain JSONL under `~/.tallystone` (or `$TALLYSTONE_HOME`). Packages are
portable JSON/Markdown.

## Install

No dependencies, Python 3.9+.

```bash
pip install .            # from a clone
pip install tallystone   # once published (alpha)
```

Or copy the single `tallystone.py` file next to your code — the core is one
stdlib-only module.

## Quick start

```bash
python3 tallystone.py            # smoke test (writes to a throwaway store)
python3 test_tallystone.py       # core tests
python3 test_bench_tallystone.py # benchmark tests (incl. negative controls)
```

```python
import tallystone as cb

cb.capture_decision(project_scope="proj", agent="chatgpt",
                    title="Use SQLite", decision="Use SQLite",
                    rationale="Simple to operate")

cb.capture_decision(project_scope="proj", agent="chatgpt",
                    title="Use Postgres", decision="Use Postgres",
                    rationale="Concurrent writers required",
                    supersedes=[<id-of-sqlite-decision>])

pkg = cb.ContextPackage(
    decisions=[d for d in cb.load_records("proj", cb.RecordKind.DECISION_RECORD)
               if d.status != cb.VerificationStatus.SUPERSEDED],
    supersession_history=cb.build_supersession_history(
        cb.load_records("proj", cb.RecordKind.DECISION_RECORD)),
)
print(pkg.to_json())        # portable package
print(pkg.to_markdown())    # human-readable handoff
```

## Benchmark — and the result we lose

A reproducible, offline benchmark (`bench_tallystone.py`) compares the structured
handoff against the baseline it must beat: a **history-aware chat summary**.
Every method is greedily filled to the *same* token budget across five seeds.

`critical_fact_preservation` (mean over seeds; higher is better) — the `ts_*`
rows are full JSON, the `ts_*_wire` rows use the compact wire encoding:

| method | 1000 | 2000 | 4000 | 8000 | 16000 |
| --- | --- | --- | --- | --- | --- |
| `ts_compact` (full JSON, before) | 0.34 | 0.53 | 0.64 | 0.86 | 0.99 |
| **`ts_compact_wire` (after)** | **0.53** | 0.65 | **0.90** | **0.99** | **0.99** |
| `ts_audit_wire` | 0.21 | 0.48 | 0.87 | 1.00 | 1.00 |
| `ts_current_wire` | 0.38 | 0.51 | 0.83 | 0.84 | 0.84 |
| `sum_terse` | 0.43 | 0.43 | 0.43 | 0.43 | 0.43 |
| `sum_verbose` | 0.45 | 0.57 | 0.57 | 0.57 | 0.57 |
| `sum_history` (strong baseline) | 0.47 | 0.71 | 0.71 | 0.71 | 0.71 |

```bash
python3 bench_tallystone.py                      # equal-budget sweep (default)
python3 bench_tallystone.py --budgets 2000,8000 --seeds 42,7,13
python3 bench_tallystone.py --single             # one head-to-head report
python3 bench_tallystone.py --profile            # where the tokens go
python3 bench_tallystone.py --holdout            # unseen scenario shapes
```

**What this honestly says:**

1. **Serialization slimming moved the curve left ~2.6x.** The compact wire
   encoding costs **4,305 tokens vs 11,339** on the default scenario (×2.63) —
   by dropping indentation (the full export is pretty-printed), eliding
   empty/default fields, and shortening keys. As a result `ts_compact_wire`
   beats the strong history-aware summary at **4,000 tokens and up** (0.90 vs
   0.71), and now also at 1,000 (0.53 vs 0.47).
2. **We still lose at 2,000 tokens** (0.65 vs 0.71). At that budget a
   history-aware summary is still slightly more token-efficient; the wire
   encoding overtakes it around ~3,000.
3. **Change history is preserved by both — the advantage is cost, not
   exclusivity.** A *history-aware* summary (`sum_history`) also reaches 1.00
   here, because it spends its whole budget restating history. So we do **not**
   claim to be the only one that can carry it. The defensible difference is that
   the structured handoff keeps history *and* more of the decisions, rationale,
   and evidence at the same budget — and when the budget is too tight to restate
   everything, the summary drops history entirely (0.00 at 1,000 tokens on the
   larger held-out shape) while the structured handoff keeps it at 1.00.

**Held-out shapes** (12/6/3 and 28/14/8 decisions/constraints/pending, reported
separately, never merged): `ts_compact_wire` reaches 0.99 and 0.78 at 4,000
tokens respectively, versus 0.71 for the summary. On the small shape it leads
from 2,000 up; on the larger shape it leads at 1,000 (0.47 vs 0.26) and from
4,000 up, while still trailing at 2,000.

**Where the tokens go** (`--profile`, default scenario): decisions dominate
(6,531 → 3,316 tokens) and the package-level `evidence` field (1,953 tokens in
the full encoding) is *omitted* from the wire because it is exactly
reconstructable from the child records. Pretty-printing overhead alone is ~808
tokens in the full encoding vs 22 in the wire.

## Compact wire format

`to_json()`/`to_dict()` is the canonical, readable, schema-anchored export and
does **not** change. The compact wire format (`to_wire_json()` /
`ContextPackage.from_wire_json()`) is a transport encoding of the same
information: no indentation, empty/default fields elided, keys shortened.
Decoding is backward-compatible (a legacy full JSON still loads) and validated:
round-trips are byte-deterministic, malformed/unknown-version input is rejected,
and per-record ids, verification status, supersession links, and evidence
provenance all survive. See `test_tallystone.py` for the round-trip, negative,
and cross-project-leakage tests.

## Why not an existing tool?

The feature list is not the moat — supersession, evidence, and decision history
exist elsewhere. The bet here is the *combination*: **local-first, no API keys,
portable open JSON/Markdown, and an honest published benchmark** that includes
where this approach loses.

## Status

`v0.1.0-alpha` — experimental. Known limitations:

- Still trails the strongest summary at the 2,000-token budget (see above).
- No first-party CLI yet (the library + JSON/Markdown is the surface).

## Naming

A *tallystone* is a marked stone used to keep count and mark a boundary — a
durable, verifiable reference point. The name was chosen after a collision check:
common single-word candidates (`baton`, `cairn`, `tessera`, `waystone`, ...) are
all taken on PyPI and/or by adjacent AI-memory projects. `tallystone` is free on
PyPI with no naming collision on GitHub.

## License

Apache-2.0 — see [LICENSE](LICENSE).
