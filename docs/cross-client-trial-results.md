# Cross-client trial results

## 2026-10-23 — Cursor Composer → Codex CLI

| Field | Value |
| --- | --- |
| Producer | Cursor Composer (export via `scripts/export_cross_client_fixture.py --agent cursor-composer`) |
| Consumer | Codex CLI `0.162.1` (`codex exec`, read-only) |
| Package | `artifacts/cross-client/handoff.json` (local, gitignored) |
| Tag baseline | built from `main` after `v0.1.0a0` docs release; transport tests are new on this branch |

### Commands

```bash
python3 test_cross_client_fidelity.py
python3 scripts/export_cross_client_fixture.py --agent cursor-composer
codex exec --skip-git-repo-check --cd "$PWD" '…verify handoff.json vs snapshot.json…'
```

### Critical-field checklist

| Group | Result |
| --- | --- |
| decisions | PASS |
| constraints | PASS |
| supersession_history | PASS |
| evidence | PASS |

Codex consumer reply (verbatim):

```json
{"client":"codex-cli","match_decisions":true,"match_constraints":true,"match_history":true,"match_evidence":true,"notes":"Compared the requested fields in handoff.json with snapshot.json; all match. meta.json was read and contains package metadata only."}
```

### Automated transport gate

`test_cross_client_fidelity.py`: 3 passed (isolated producer/consumer stores, wire round-trip, budget trim keeps supersession).

### Gaps

- **Claude Code leg not run.** `claude -p` failed with `OAuth session expired and could not be refreshed` on this machine. Re-run after `claude` login to complete Claude Code ↔ Codex bidirectionally.
- **MCP host tool lifecycle verified in automation.** Direct stdio MCP host testing now exercises `context_checkpoint`, `context_resume`, and `context_handoff` in `test_mcp_packaged_entrypoint.py` on the packaged wheel. Full GUI client integration (e.g. Claude Desktop) remains an open community trial.
- This trial shows two *different* agent interfaces agree on package fields; it is not independent external-user adoption evidence.

## 2026-11-24 — MCP stdio Host Client Lifecycle (test_mcp_packaged_entrypoint.py)

| Field | Value |
| --- | --- |
| Producer | `handoffstone-mcp` packaged CLI via stdio JSON-RPC (`context_checkpoint`, `context_handoff`) |
| Consumer | `handoffstone-mcp` packaged CLI via stdio JSON-RPC (`context_resume`) |
| Transport | MCP Stdio protocol `2025-06-18` across isolated client processes |
| Storage | `HANDOFFSTONE_HOME` JSONL persistence + Git worktree state binding |

### Critical-field checklist

| Group | Result |
| --- | --- |
| decisions | PASS (`included_decisions=1`, decision title and rationale verified) |
| working_state | PASS (`active_task` restored identically in `context_resume`) |
| handoff persistence | PASS (`HandoffRecord` generated with `handoff_id`) |
| security isolation | PASS (out-of-bounds `repo_path` rejected with `repo_outside_allowed_root`) |

### Automated gate

`test_mcp_packaged_entrypoint.py::PackagedMcpEntryPoint::test_end_to_end_mcp_host_lifecycle`: PASSED against the built wheel distribution.

## Template for the next run

```markdown
## YYYY-MM-DD — ClientA → ClientB

| Field | Value |
| --- | --- |
| Producer | … version … |
| Consumer | … version … |

### Critical-field checklist
| Group | Result |
| decisions | |
| constraints | |
| supersession_history | |
| evidence | |

### Notes / diffs
…
```
