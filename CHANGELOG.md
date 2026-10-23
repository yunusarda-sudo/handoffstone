# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [PEP 440](https://peps.python.org/pep-0440/) versioning.

## [Unreleased]

### Added

- Cross-client transport fidelity tests and a documented live-trial protocol
  (`test_cross_client_fidelity.py`, `docs/cross-client-trial.md`).
- Fixture export helper `scripts/export_cross_client_fixture.py` for producer →
  consumer product trials.
- PEP 639 license metadata and release checks that verify the tag against the
  package version declared in `pyproject.toml`.
- Optional MCP stdio adapter with packaged `handoffstone-mcp` command, Git-bound
  checkpoint/resume/handoff tools, and explicit local trust boundaries.
- Reliability hardening and cross-version MCP contract tests.

## [0.1.0a1] - 2026-10-24

Second public alpha, released from the merged PEP 639 and reproducible release
workflow changes. The published artifacts contain the core library; MCP support
is still under review in the next development change.

## [0.1.0a0] - 2026-10-23

First public alpha. Portable, stdlib-only context handoffs for AI agents.

### Added

- Core record model: project context, decisions, constraints, working state,
  checkpoints, handoffs, and evidence references.
- Supersession history and budget-aware `ContextPackage` export (JSON, Markdown,
  compact wire format).
- Local JSONL store under `~/.handoffstone` (or `$HANDOFFSTONE_HOME`).
- Consumer chat export helpers and an equal-budget benchmark with negative
  controls.
- Published JSON Schema (`schema/handoff.schema.json`) and a schema-contract test
  that accepts `conversation` evidence.
- GitHub Actions CI on Python 3.10, 3.11, and 3.13 (tests, schema check, wheel
  install smoke).

### Security

- Project scopes are filename components only; path separators and store
  symlinks are rejected.
- New store files are created with mode `0600` on POSIX.

### Changed

- Declared minimum Python version is 3.10 (matches runtime union type usage).

[0.1.0a0]: https://github.com/yunusarda-sudo/handoffstone/releases/tag/v0.1.0a0
[0.1.0a1]: https://github.com/yunusarda-sudo/handoffstone/releases/tag/v0.1.0a1
