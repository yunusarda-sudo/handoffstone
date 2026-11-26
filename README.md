# handoffstone

[![CI](https://github.com/yunusarda-sudo/handoffstone/actions/workflows/ci.yml/badge.svg)](https://github.com/yunusarda-sudo/handoffstone/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> Portable, verifiable, decision-aware context handoffs for AI agents.

## What it is

When work moves between agents (ChatGPT → Claude → Codex → OpenCode → ...), a
chat summary loses the things that actually matter: *why* a decision was made,
*what evidence* it rests on, and *how it changed*. `handoffstone` is a small,
dependency-free core for carrying that across the handoff:

- **Decisions** with rationale, rejected alternatives, and verification status
- **Constraints** (non-negotiable rules/preferences) with category and severity
- **Change history** — which decision replaced which, and why (supersession)
- **Evidence** locators (file / commit / test / url / conversation) as provenance
- **Working state** — active task, blockers, next action, completed/remaining progress
- **Budget-aware packaging** — deterministically fits a package into a token budget

It is **local-first and stdlib-only**: no network, no API keys, no servers, no
database. State is plain JSONL under `~/.handoffstone` (or `$HANDOFFSTONE_HOME`). Packages are
portable JSON/Markdown.

## Install

No runtime dependencies, Python 3.10+.

```bash
# From the GitHub release tag (v0.1.0a3 includes the MCP adapter)
python -m pip install "git+https://github.com/yunusarda-sudo/handoffstone.git@v0.1.0a3"

# Or from a clone of main
python -m pip install .
```

The package provides:
1. `handoffstone`: the core library module (`import handoffstone as cb`).
2. `handoffstone-mcp`: the stdio MCP bridge command exposing `context_checkpoint`, `context_resume`, and `context_handoff`.

See [MCP setup and security boundaries](docs/MCP.md).
See [CHANGELOG.md](CHANGELOG.md) for release history, and [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## Quick start

```bash
# Run core test suite (43 checks)
python3 test_handoffstone.py

# Run benchmark tests (incl. negative controls)
python3 test_bench_handoffstone.py

# Run all 157 discovered tests across the entire repository
python3 -m unittest discover -s . -p "test_*.py"

# Run automated maintainer triage check (AST stdlib-only & negative controls)
python3 scripts/maintainer_pr_checklist.py --check
```

### Python API Example

```python
import handoffstone as cb

# 1. Capture initial technical decision
first = cb.capture_decision(
    project_scope="my-proj",
    agent="agent-alpha",
    title="Database Choice",
    decision="Use SQLite with WAL",
    rationale="Local-first, zero ops overhead",
    alternatives=[{"option": "PostgreSQL", "reason_rejected": "Ops overhead unjustified"}],
)

# 2. Record an architectural constraint
cb.capture_constraint(
    project_scope="my-proj",
    agent="agent-alpha",
    constraint="Core library must stay stdlib-only",
    category="architecture",
    severity="critical",
)

# 3. Supersede with a newer decision when requirements evolve
second = cb.capture_decision(
    project_scope="my-proj",
    agent="agent-alpha",
    title="Database Choice",
    decision="Use PostgreSQL",
    rationale="Concurrent multi-writer workloads required",
    supersedes=[first.id],
)

# 4. Assemble and fit package to token budget
records = cb.load_records("my-proj", cb.RecordKind.DECISION_RECORD)
pkg = cb.ContextPackage(
    decisions=[d for d in records if d.status != cb.VerificationStatus.SUPERSEDED],
    constraints=cb.load_records("my-proj", cb.RecordKind.CONSTRAINT_RECORD),
    supersession_history=cb.build_supersession_history(records),
    created_by="agent-alpha",
)

# Fit into a 2,000 token budget for handover
fitted = cb.fit_package_to_budget(pkg, max_tokens=2000, wire="compact")

print(fitted.to_json())        # Schema-anchored portable JSON
print(fitted.to_wire_json())   # Space-efficient compact wire encoding
print(fitted.to_markdown())    # Human-readable Markdown summary
```

## MCP Integration

When installed, `handoffstone-mcp` connects to any standard MCP host (Claude Desktop, Cursor, Codex, Antigravity) over stdio:

```json
{
  "mcpServers": {
    "handoffstone": {
      "command": "handoffstone-mcp"
    }
  }
}
```

Key tools exposed:

- `context_checkpoint`: Attaches verified decisions and working state to the current Git commit/branch.
- `context_resume`: Restores active decisions, constraints, and tasks, verifying Git worktree freshness.
- `context_handoff`: Validates and exports a clean context package for the receiver agent.


See [docs/MCP.md](docs/MCP.md) for configuration examples and security boundaries.

## Benchmark — and the result we lose

A reproducible, offline benchmark (`bench_handoffstone.py`) compares the structured
handoff against the baseline it must beat: a **history-aware chat summary**.
Every method is greedily filled to the *same* token budget across five seeds.

`critical_fact_preservation` (mean over seeds; higher is better) — the `ts_*`
rows are full JSON, the `ts_*_wire` rows use the compact wire encoding:

| method | 1000 | 2000 | 4000 | 8000 | 16000 |
| --- | --- | --- | --- | --- | --- |
| `ts_compact` (full JSON, before) | 0.34 | 0.53 | 0.64 | 0.86 | 0.99 |
| **`ts_compact_wire` (after)** | 0.47 | **0.73** | **0.96** | **0.99** | **0.99** |
| `ts_audit_wire` | 0.21 | 0.48 | 0.87 | 1.00 | 1.00 |
| `ts_current_wire` | 0.38 | 0.51 | 0.83 | 0.84 | 0.84 |
| `sum_terse` | 0.43 | 0.43 | 0.43 | 0.43 | 0.43 |
| `sum_verbose` | 0.45 | 0.57 | 0.57 | 0.57 | 0.57 |
| `sum_history` (strong baseline) | 0.47 | 0.71 | 0.71 | 0.71 | 0.71 |

```bash
python3 bench_handoffstone.py                      # equal-budget sweep (default)
python3 bench_handoffstone.py --budgets 2000,8000 --seeds 42,7,13
python3 bench_handoffstone.py --single             # one head-to-head report
python3 bench_handoffstone.py --profile            # where the tokens go
python3 bench_handoffstone.py --holdout            # unseen scenario shapes
```

**What this honestly says:**

1. **Serialization slimming moved the curve left ~2.6x:** The compact wire
   encoding costs **4,305 tokens vs 11,339** on the default scenario (×2.63) —
   by dropping indentation, eliding empty/default fields, and shortening keys.
2. **Prioritizing constraints closed the 2,000-token deficit:** In `v0.1.0a3`,
   fitting constraints before decisions restored 100% constraint recall under tight
   budgets, lifting the 2k score from 0.65 to **0.73** and beating the rival summary
   baseline (0.71). At 4k tokens and up, structured wire decisively dominates (0.96 vs 0.71).
   See [Benchmark Fairness Review](docs/BENCHMARK_FAIRNESS_REVIEW.md) for full token profiles.
3. **Change history is preserved by both — the advantage is cost, not
   exclusivity:** A *history-aware* summary (`sum_history`) also reaches 1.00
   when given sufficient budget, because it spends its whole text restating history.
   The defensible difference is that the structured handoff preserves history *and*
   structured constraints and decisions at the same budget — and when tokens get extremely
   scarce, the chat summary drops change history entirely while `handoffstone` keeps it.
4. **Where the structured format still loses:** Under extreme starvation (1,000 tokens),
   natural language prose summaries tie with the wire format (0.47 vs 0.47) because
   JSON framing overhead (syntax punctuation and keys) consumes unavoidable token bytes.

**Held-out shapes** (12/6/3 and 28/14/8 decisions/constraints/pending, reported
separately, never merged): `ts_compact_wire` reaches 0.99 and 0.78 at 4,000
tokens respectively, versus 0.71 for the summary.

## Compact wire format

`to_json()`/`to_dict()` is the canonical, readable, schema-anchored export and
does **not** change. The compact wire format (`to_wire_json()` /
`ContextPackage.from_wire_json()`) is a transport encoding of the same
information: no indentation, empty/default fields elided, keys shortened.
Decoding is backward-compatible (legacy full JSON still loads) and validated:
round-trips are byte-deterministic, malformed/unknown-version input is rejected,
and per-record ids, verification status, supersession links, and evidence
provenance all survive. See `test_handoffstone.py` for the round-trip, negative,
and cross-project-leakage tests.

## Why not an existing tool?

The feature list is not the moat — supersession, evidence, and decision history
exist elsewhere. The bet here is the *combination*: **local-first, no API keys,
zero runtime dependencies, portable open JSON/Markdown, and an honest published benchmark**
that documents where this approach wins and where it loses.

## Status

`v0.1.0a3` — public alpha.
- **Core Library:** 92% test coverage, stdlib-only, zero dependencies.
- **MCP Adapter:** `handoffstone-mcp` with automated end-to-end stdio host lifecycle tests (`test_mcp_packaged_entrypoint.py`) and protocol unit tests (`test_mcp_protocol_unit.py`).
- **Token Efficiency:** Surpasses the history-aware chat summary baseline at 2,000 tokens and above.
- **Cross-Client Trials:** Cursor Composer → Codex CLI and automated MCP stdio lifecycle pass; live model-turn trials tracked in [issue #1](https://github.com/yunusarda-sudo/handoffstone/issues/1).
- **CI / Quality Gate:** 157 automated tests across Python 3.10, 3.11, 3.12, 3.13, and 3.14 with AST import isolation and negative controls preservation.

### Reliability boundaries

The P0 hardening keeps JSONL and the existing data formats. Canonical VERIFIED
records require usable, explicitly attested evidence. Recognized sensitive
content and unsafe/mismatched scopes are rejected; write failures propagate,
and corrupted/unavailable stores are distinct from an empty store. Safe legacy
records remain readable, but previously unsafe inputs intentionally fail closed.

See [P0 reliability and compatibility](docs/P0_RELIABILITY.md) for the exception
API and limits. Run `python3 -B -m unittest -v test_reliability` for the
negative/regression suite.

## Community & Maintainer Guides

- [Contributing](CONTRIBUTING.md) — fork, pull request, and contributor requirements
- [Documentation Index](docs/README.md) — guide to all architecture docs
- [Maintainer Playbook](docs/MAINTAINER_PLAYBOOK.md) — PR triage, Codex review, and release flow
- [Benchmark Review](docs/BENCHMARK_FAIRNESS_REVIEW.md) — token budget analysis and methodology
- [Security Policy](SECURITY.md) — private vulnerability reporting
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
