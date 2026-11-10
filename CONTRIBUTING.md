# Contributing

`handoffstone` is a v0.1.0-alpha. The most valuable contributions right now are the ones
that make the core **more useful and more honest**, not larger.

Participation is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
Report security problems privately, as described in [SECURITY.md](SECURITY.md).
Use the bug and feature issue forms for concrete defects and proposals; use
[Discussions](https://github.com/yunusarda-sudo/handoffstone/discussions) for
open design questions.

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
python3 -m pip install -e '.[dev]'     # jsonschema for the schema contract
python3 test_handoffstone.py           # core: expects 41 passing
python3 test_storage_security.py       # local store hardening
python3 test_cross_client_fidelity.py  # producer/consumer transport gate
python3 test_mcp_bridge.py             # MCP protocol and core integration
python3 test_bench_handoffstone.py     # benchmark: expects 25 passing
python3 -B -m unittest -v test_reliability  # P0 public-boundary regressions
python3 test_schema_contract.py        # canonical export vs JSON Schema
python3 handoffstone.py                # smoke test (throwaway store)
python3 bench_handoffstone.py          # equal-budget sweep
python3 bench_handoffstone.py --profile  # token profile
```

Live Claude Code ↔ Codex trials follow
[docs/cross-client-trial.md](docs/cross-client-trial.md).

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

## Contributing from outside

You do not need write access to this repository.

1. Fork the repository and create a branch from `main`.
2. Keep the change to one behavior, and add or update a test.
3. Open a pull request against `main`. `@yunusarda-sudo` is requested for review.
4. Wait for CI on Python 3.10, 3.11, 3.12, 3.13, and 3.14.

A maintainer merges. `main` rejects direct pushes and force-pushes, including from maintainers: the branch requires a pull request and those five green checks. A second approving review is not required, because there is one maintainer. The maintainer still decides what lands.

These will not be merged:

- A third-party import in `handoffstone.py`
- A weaker or deleted negative control
- A benchmark or README change that hides a loss
- A commit that contains secrets, tokens, or a real project store

Start with the open [`help wanted` issues](https://github.com/yunusarda-sudo/handoffstone/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22). A written benchmark-fairness review on issue #2 is a useful first contribution and does not require a code change. Maintainer automation is not an outside task.

## Packaging note

The core is a single module (`handoffstone.py`). Keep it importable with no other
files present.

## Releases

1. Update `CHANGELOG.md` under a new version heading and bump
   `project.version` in `pyproject.toml` when the public API or install story
   changes.
2. Open a pull request; wait for CI on Python 3.10, 3.11, 3.12, 3.13, and 3.14.
3. After merge, tag from `main` as `vX.Y.ZaN` (match `pyproject.toml`) and
   publish a GitHub Release whose notes summarize the changelog section.
4. Do not claim a PyPI package exists until one is actually published.
