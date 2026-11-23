# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [PEP 440](https://peps.python.org/pep-0440/) versioning.

## [Unreleased]

## [0.1.0a3] - 2026-11-24

Fourth public alpha. Renames the MCP adapter module for clean PyPI distribution, prioritizes constraints in budget fitting to surpass rival chat summaries at 2k tokens, adds the maintainer playbook and automated triage checklist, and adds the PyPI Trusted Publishing workflow.

### Changed

- Prioritized constraints before decisions in `_PACKAGE_FIT_PRIORITY` and `fit_package_to_budget`, eliminating constraint starvation under tight token budgets and raising 2k wire format critical fact preservation above the history-aware summary baseline (0.733 vs 0.714).
- Renamed the top-level MCP adapter module from generic `mcp_stdio` to namespaced `handoffstone_mcp` to prevent namespace collisions upon PyPI installation, while preserving the packaged `handoffstone-mcp` CLI entrypoint.
- Outside contributions enter through forks and pull requests. `main` requires a pull request and green CI on Python 3.10–3.14 before it can move, including for maintainers.

### Added

- PyPI Trusted Publishing GitHub Actions workflow (`.github/workflows/publish.yml`) publishing via OIDC on published release.
- Maintainer playbook and automated triage checklist script (`scripts/maintainer_pr_checklist.py`, `docs/MAINTAINER_PLAYBOOK.md`) for PR reviews, Codex agent triage, and release publishing flow.
- Benchmark fairness and token efficiency review (`docs/BENCHMARK_FAIRNESS_REVIEW.md`).
- Contributor Covenant, GitHub issue forms, a pull request template, and a documentation index.
- Private vulnerability reporting as the security contact. The published maintainer email is the fallback; the GitHub profile has no public email.

## [0.1.0a2] - 2026-10-24

Third public alpha. Adds the optional local MCP stdio adapter, launched by the
packaged `handoffstone-mcp` command, with Git-bound checkpoint, resume, and
handoff tools.

### Added

- Optional MCP stdio adapter with a packaged `handoffstone-mcp` command,
  Git-bound checkpoint/resume/handoff tools, and explicit local trust
  boundaries.
- Reliability hardening and cross-version MCP contract tests.

### Changed

- Bind MCP resume state to Git branch, commit, index, tracked changes, and
  untracked file contents.
- Use unique private atomic-write temporary files and distinguish failures
  before replacement from uncertain directory durability after replacement.

## [0.1.0a1] - 2026-10-24

Second public alpha. The published artifacts contain the core library; the MCP
adapter is introduced in v0.1.0a2.

### Added

- Cross-client transport fidelity tests and a documented live-trial protocol
  (`test_cross_client_fidelity.py`, `docs/cross-client-trial.md`).
- Fixture export helper `scripts/export_cross_client_fixture.py` for producer →
  consumer product trials.
- PEP 639 license metadata and tag-to-project-version checks in release
  validation.

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
[0.1.0a2]: https://github.com/yunusarda-sudo/handoffstone/releases/tag/v0.1.0a2
[0.1.0a3]: https://github.com/yunusarda-sudo/handoffstone/releases/tag/v0.1.0a3
