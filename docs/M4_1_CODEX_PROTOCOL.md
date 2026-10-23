# M4.1 — Real Codex MCP Integration Validation Report

Worktree: `/Users/yunusardaguney/handoffstone-m4-p0`, branch
`codex/m4-handoffstone-stdio`, base `e22c6ff`. The dirty working tree in
`~/handoffstone`, every pilot file and all global Codex config were untouched;
`CODEX_HOME` was pointed at `/tmp/m41/codex-home` (disposable) so nothing was
written to `~/.codex`.

## Phase A — free protocol validation (no model calls)

| Check | Status | Evidence |
| --- | --- | --- |
| Codex CLI version recognized | PASS | `codex-cli 0.162.1`; `codex mcp` subcommands available (list/get/add/remove) |
| Isolated `CODEX_HOME` config read | PASS | `CODEX_HOME=/tmp/m41/codex-home codex mcp list --json` returns the handoffstone server with transport stdio, env passthrough, `enabled: true` |
| Real MCP handshake (`initialize`) | PASS | `exec_stderr.log`: `rmcp::service: Service initialized as client peer_info=ServerPeerInfo { protocol_version: ProtocolVersion("2025-06-18"), server_info: Implementation { name: "handoffstone-m4", version: "0.1.0-prototype" } }` |
| Real tool discovery (`tools/list`) | PASS | `MCP binding catalog materialized ... tool_count=3 tool_definition_json_bytes=1330` (emitted at startup and again per turn) |
| Session-level server attach | PASS | `event.name="codex.conversation_starts" ... mcp_servers="handoffstone" ... mcp_server_count=1` |
| Zero-cost protocol run | PASS | `codex exec` without API credentials: TURN failed with 401 before any API request; store dir `/tmp/m41/store` stayed empty (no writes) |
| JSON-RPC error flow (server side) | PASS | 23 test suite incl. old-core rejection, invalid params, parse errors (no fake success) |
| Git validation deepening | PASS | Bridge now records branch + HEAD SHA + **dirty-worktree digest** (`git status --porcelain -uall`, SHA-256, sorted) at checkpoint; `context_resume` returns `worktree_changed` (ready=false) when the digest differs, plus pre-existing `stale_head`/`stale_branch`/`project_mismatch` gates |
| Real-core compatibility | PASS | New `RealCoreCompat` tests run the bridge against the real `e22c6ff` core: checkpoint+resume end-to-end and corrupt-store → `store_corrupt` |
| Evidence locator validation | PASS | file locators verified only inside the bound repo root; traversal/absolute escapes are not verified; commit locators via `git cat-file -e` |

Test status: `test_mcp_bridge.py` 25/25 (23 fake-core contract + 2 real-core
compat, both classes green), real core suites in the worktree: core 41/41,
`test_reliability` OK, bench 25/25.

## Phase B — live Codex memory write/read: NOT RUN (user consent required)

Protocol discovery is proven; a tool *invocation* through Codex requires a
model turn, which requires the paid call gate. The planned run (fixed budget,
one-shot, sessions A/B over the bridge, cross-scope invisibility, usage
capture with no zero-cost assumption) is ready to execute on approval.

## Phase C — benchmark readiness

20-scenario AGENTS.md vs Basic Memory vs Handoffstone comparison design stands
from the pilot work (arms, budgets, oracle). Open item made concrete by the
M4.1 review: the fixture baseline arm must give both systems *equal information
access* and grade the real task completion, not stale-branch stridency — same
facts, same budget, action/evidence-based scoring, no model calls in prep.
Live benchmarking again requires the paid gate, so Phase C stays in prep
without running results.

## Known limitations carried forward

1. Multi-record checkpoints are atomic within one process (write-then-rename
   batch), but there is no multi-process writer locking: single-writer only.
2. `fit_package_to_budget` logic is an approximate estimator.
3. Codex-side tool invocation and usage reporting are Phase B items.
