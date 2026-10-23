# Contributing

`handoffstone` is a v0.1.0-alpha. The most valuable contributions right now are the ones
that make the core **more useful and more honest**, not larger.

## Ground rules

- **Stdlib only in the core.** `handoffstone.py` must keep zero third-party imports.
  Network access, API keys, and external services are out of scope by design.
- **Tests must keep their teeth.** `test_bench_handoffstone.py` contains negative
  controls so the metrics can't silently become blind (e.g. always 1.0). Do not
  weaken or delete them. If you change a metric, keep a test proving it moves.
- **Publish results even when we lose.** If a change or a new baseline reverses
  a benchmark result, update README rather than tuning the benchmark.

## Running the checks

```bash
python3 test_handoffstone.py           # core: expects 41 passing
python3 test_bench_handoffstone.py     # benchmark: expects 25 passing
python3 handoffstone.py                # smoke test (throwaway store)
python3 bench_handoffstone.py          # equal-budget sweep
python3 bench_handoffstone.py --profile  # token profile
```

## High-value areas

1. **Serialization slimming** — reduce per-decision token overhead so the
   equal-budget curve moves left (the known weakness). Must not lose
   supersession, rationale, or evidence provenance. The compact wire format
   (`to_wire_json` / `from_wire_json`) is where this happens; keep its
   round-trip, malformed-input, and cross-project-leakage tests green.
2. **Real cross-client trials** — capture → handoff between two genuinely
   different agent clients, and document what broke.
3. **Schema review** — `schema/handoff.schema.json` should match
   `ContextPackage.to_dict()` exactly (the canonical export, not the wire form).

## Packaging note

The core is a single module (`handoffstone.py`). Keep it importable with no other
files present.

## Releases

1. Update `CHANGELOG.md` under a new version heading and bump
   `project.version` in `pyproject.toml` when the public API or install story
   changes.
2. Open a pull request; wait for CI on Python 3.10, 3.11, and 3.13.
3. After merge, tag from `main` as `vX.Y.ZaN` (match `pyproject.toml`) and
   publish a GitHub Release whose notes summarize the changelog section.
4. Do not claim a PyPI package exists until one is actually published.
