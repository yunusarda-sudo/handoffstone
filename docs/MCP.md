# MCP stdio adapter

The optional `handoffstone-mcp` command exposes checkpoint, resume, and handoff
tools over MCP JSON-RPC stdio. It is a local integration for compatible MCP
hosts; it does not provide a hosted service or product UI. The published
`0.1.0a1` artifact predates this adapter; install from a trusted checkout that
contains the adapter until a later release includes it.

Install the release artifact or a trusted checkout, then configure the MCP host
to launch `handoffstone-mcp` with these environment variables:

- `HANDOFFSTONE_HOME`: an absolute path to the private local JSONL store.
- `HANDOFFSTONE_ALLOWED_REPO_ROOT`: an absolute path containing repositories
  the server may inspect. The server resolves the path and rejects repository
  roots outside it.

For example, a Codex MCP server entry can use `command = "handoffstone-mcp"`
and pass both variables in its `env` map. Keep the store private and only enable
the adapter for MCP clients you trust: checkpoint and handoff tools write local
project context. The resume tool reads context only from the matching project
scope and Git root/branch/commit. A changed worktree is reported as stale.

The adapter is stdio-only and dependency-free. It does not authenticate the MCP
client, lock the JSONL file across concurrent server processes, or prove that
evidence locators remain true. Do not run multiple writers against the same
store concurrently. These limits are explicit and should be considered before
using it in an automated or shared environment.

Run `python test_mcp_bridge.py` for protocol, validation, and persistence checks.
The CI package smoke test installs the wheel and invokes the generated command
from a directory outside the source checkout.
