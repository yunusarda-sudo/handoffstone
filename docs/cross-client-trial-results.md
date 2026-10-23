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
- **MCP host** using a `context_handoff` tool is still unchecked (issue #1).
- This trial shows two *different* agent products can agree on package fields; it is not independent external-user adoption evidence.

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
