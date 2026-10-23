# Cross-client handoff trial

Tracks [issue #1](https://github.com/yunusarda-sudo/handoffstone/issues/1): prove a
`handoffstone` package survives a move between *different* agent clients.

## What is automated today

```bash
python3 test_cross_client_fidelity.py
```

These tests use two isolated `HANDOFFSTONE_DIR` trees (producer / consumer
processes). They are a **transport fidelity gate**, not a substitute for a live
Claude Code ↔ Codex product trial.

Covered:

- Canonical JSON export → import in a separate store
- Compact wire round-trip of critical fields
- Budget-trimmed packages still keep supersession links

## Live product protocol

### 1. Produce a fixture

```bash
python3 scripts/export_cross_client_fixture.py --agent claude-code
```

Artifacts land in `artifacts/cross-client/` (gitignored):

| File | Role |
| --- | --- |
| `handoff.json` | Canonical, schema-anchored package |
| `handoff.wire.json` | Compact transport encoding |
| `snapshot.json` | Critical-field expected values |

### 2. Consume on a second client

On the receiving client (example: Codex CLI):

1. Install the same tagged release the producer used.
2. Load `handoff.json` with `ContextPackage.from_json`.
3. Diff against `snapshot.json` for decisions, constraints, supersession
   history, and evidence.

Non-interactive Codex check (adjust paths):

```bash
codex exec --skip-git-repo-check "$(cat <<'EOF'
Read artifacts/cross-client/handoff.json and artifacts/cross-client/snapshot.json.
Using only those files, print a JSON object with keys match_decisions,
match_constraints, match_history, match_evidence (booleans) and notes (string).
Do not modify any files.
EOF
)"
```

Claude Code equivalent once authenticated:

```bash
claude -p --bare "Read artifacts/cross-client/handoff.json and snapshot.json. Report whether decisions, constraints, supersession history, and evidence match. Do not modify files."
```

### 3. Report results

Append a dated section to [cross-client-trial-results.md](cross-client-trial-results.md)
with:

1. Client names and versions
2. Commands run
3. Pass/fail per critical field group
4. Any package JSON diffs (redact secrets)

## Out of scope for the alpha gate

- Claiming ecosystem adoption from synthetic stars or downloads
- Weakening benchmark negative controls to make a trial “pass”
