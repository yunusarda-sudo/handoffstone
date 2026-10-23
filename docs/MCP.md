# MCP stdio adapter

The optional `handoffstone-mcp` command exposes checkpoint, resume, and handoff
tools over MCP JSON-RPC stdio. It is a local integration for compatible MCP
hosts; it does not provide a hosted service or product UI. The published
`0.1.0a1` artifact predates this adapter; `0.1.0a2` is the first release to
include it.

Install the `v0.1.0a2` GitHub release or a trusted checkout, then configure the
MCP host to launch `handoffstone-mcp` with these environment variables:

- `HANDOFFSTONE_HOME`: an absolute path to the private local JSONL store.
- `HANDOFFSTONE_ALLOWED_REPO_ROOT`: an absolute path containing repositories
  the server may inspect. The server resolves the path and rejects repository
  roots outside it.

For example, a Codex MCP server entry can use `command = "handoffstone-mcp"`
and pass both variables in its `env` map. Keep the store private and only enable
the adapter for MCP clients you trust: checkpoint and handoff tools write local
project context. The resume tool reads context only from the matching project
scope and Git root/branch/commit. Its worktree identity includes the index,
tracked changes, and untracked file contents; a changed worktree is reported as
stale even when Git's status summary stays the same.

Checkpoint batches use a unique private temporary file, sync its contents, and
atomically replace the scope store. On systems that support directory syncing,
the adapter syncs the store directory too. A pre-replacement failure returns
`write_failed_atomic_no_partial`, meaning the prior store remains in place. If
replacement succeeded but directory syncing fails, it returns
`write_applied_durability_uncertain`: the new data is visible, but durability
across a sudden system failure is uncertain. Read the store before retrying to
avoid duplicating the operation. Windows does not support this directory-sync
step; the adapter syncs file contents and atomically replaces the file there.

The adapter is stdio-only and dependency-free. It does not authenticate the MCP
client, lock the JSONL file across concurrent server processes, or prove that
evidence locators remain true. Do not run multiple writers against the same
store concurrently. These limits are explicit and should be considered before
using it in an automated or shared environment.

Run `python test_mcp_bridge.py` for protocol, validation, and persistence checks.
The CI package smoke test installs the wheel and invokes the generated command
from a directory outside the source checkout.
