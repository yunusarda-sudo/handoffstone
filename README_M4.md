# Handoffstone M4 — stdio MCP bridge prototype

This package contains **only two proposed source files**, `mcp_stdio.py` and
`test_mcp_bridge.py`. It has **not** been applied or committed to the user's
local Mac repositories. It does not modify `handoffstone.py`.

## Intended environment

- Python 3.9+ with local Handoffstone P0 reliability module importable as
  `handoffstone` from the same folder.
- P0 exceptions: `StoreWriteError`, `StoreCorruptionError`,
  `StoreUnavailableError`, `UnsafeContentError`, `InvalidScopeError`,
  `VerificationError`.
- Set `HANDOFFSTONE_HOME` to an **absolute, dedicated** JSONL storage folder.
  This is the variable used by the observed public core. Do not substitute
  `HANDOFFSTONE_PATH` without confirming local P0 code supports it.
- Set `HANDOFFSTONE_ALLOWED_REPO_ROOT` to the absolute, allowed Git workspace
  parent. MCP repo arguments must resolve under this root.

## Copy into a separate local worktree

Do not change the dirty `fix/p0-core-reliability` working tree or the other
session's untracked files. Example (adjust source directory for downloaded ZIP):

```sh
cd ~/handoffstone
git worktree add -b codex/m4-handoffstone-stdio /tmp/handoffstone-m4-p0 e22c6ff
cp /path/to/unpacked/mcp_stdio.py /tmp/handoffstone-m4-p0/
cp /path/to/unpacked/test_mcp_bridge.py /tmp/handoffstone-m4-p0/
cd /tmp/handoffstone-m4-p0
python3 test_mcp_bridge.py
python3 test_handoffstone.py
# If present on this worktree: python3 test_reliability.py
```

The test file creates its own temporary fake P0 core and repositories. It is
**NOT** a test of the actual local P0. A separate real-P0 compatibility test
is mandatory before integrating it with Codex or ARDA.

## Direct stdio smoke test

Only in an isolated environment, not in your real memory directory:

```sh
export HANDOFFSTONE_HOME=/tmp/m4-test-store
export HANDOFFSTONE_ALLOWED_REPO_ROOT=/tmp/m4-test-workspace
python3 mcp_stdio.py
```

Send newline-delimited JSON-RPC `initialize` and `tools/list` on stdin. The
server writes only JSON-RPC responses to stdout. `context_checkpoint`,
`context_resume` and `context_handoff` are exposed by `tools/list`.

No live Codex execution, paid API calls, background services, or global Codex
configuration modifications were performed here.

## Security and correctness boundaries

1. **P0 required:** Public `main` can silently discard load/write failures.
   The bridge detects the absence of P0 error types and fails closed.
2. **Scope and Git binding:** Project scopes are restricted to safe file-name
   characters; checkpoint stores repository root, branch and HEAD. Wrong
   repository, different branch or new HEAD prevents resume from returning
   actionable context. This is intentionally conservative; a new commit needs
   a new checkpoint.
3. **Evidence:** File existence and Git commit presence are locator checks,
   not proof that a claim is true. Client requests to mark a new decision
   `verified` are rejected pending an independent evidence verifier. Previous
   `verified` records are downgraded if their locators are now missing.
4. **Secrets:** The bridge scans nested incoming/outgoing data using P0's
   `detect_secrets`; the local P0 core must still reject unsafe records on
   persistence. Regex scans cannot guarantee detection of every secret.
5. **JSONL atomicity (M4.1 update):** `context_checkpoint` now writes every
   record of one call (decisions + superseded counterparts + checkpoint) as a
   single atomic swap (`write-then-rename`, fsync on file and directory). A
   failure before the swap leaves the store byte-identical and reports
   `write_failed_atomic_no_partial`; partial multi-record state cannot occur.
   Superseded records are rewritten inside the same batch with a bumped
   `created_at` so deduplication keeps the updated version.
6. **Concurrency gap:** No multi-process writer locking is supplied by this
   bridge. The atomic swap is single-writer only; use single-writer pilot.
7. **Uncommitted changes (M4.1 update):** Closed. Resolved via
   `git status --porcelain -uall` digest; a dirty tree blocks reassembly with
   `worktree_changed` and the digest is persisted in the checkpoint.
8. **Budget:** `fit_package_to_budget` is an approximate token estimator,
   not measured model-token accounting. Non-included decisions are counted.
9. **Trust boundary:** MCP content is data, not instructions. The bridge does
   not enforce any ARDA runtime execution policy or sandbox.

## Results obtained in the isolated assistant environment

- **20 / 20 PASS** on subprocess-based MCP contract tests using a temporary,
  deliberately simplified, P0-shaped **fake core**.
- Separately created processes performed checkpoint and resume; simulated
  corruption, missing store config, stale Git branch/HEAD, scope isolation,
  secret rejection, failed writes and supersession handling.
- **NOT RUN:** local P0 compatibility/regression suite, actual Codex MCP
  negotiation/usage, real agent resume, AGENTS.md-only vs Handoffstone
  performance baseline, Basic Memory 20-scenario comparison.

## Next acceptance gate

Run the bridge against the exact P0 `e22c6ff` core, test corruption handling,
store failure injection and scope isolation with real JSONL; then add a
**single-commit checkpoint anchor / transaction or equivalent** and dirty-tree
identity detection. Only after that run controlled live Codex MCP with the
user's explicit consent, followed by the same-budget AGENTS.md and Basic
Memory comparisons using action/evidence-based scoring.
