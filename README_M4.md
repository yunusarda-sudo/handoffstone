# M4 prototype notes — archived

This file preserves the original M4 design notes. It is **not** a current
installation guide or a statement that the MCP adapter is part of a released
package.

## Current status

- Handoffstone requires Python 3.10 or newer.
- The published `v0.1.0a1` release contains the core library and does not contain
  the MCP adapter.
- The adapter and its packaging are under review in [PR #11](https://github.com/yunusarda-sudo/handoffstone/pull/11).
- Current setup and trust boundaries are in [MCP documentation](docs/MCP.md).
- Core persistence guarantees and failure behavior are in
  [P0 reliability notes](docs/P0_RELIABILITY.md).

## Historical scope

M4 proposed a dependency-free JSON-RPC stdio server with explicit
`HANDOFFSTONE_HOME` and `HANDOFFSTONE_ALLOWED_REPO_ROOT` settings. The current
branch implementation has three tools: checkpoint, resume, and handoff. It
binds checkpoints to repository root, branch, commit, Git index, tracked
working-tree changes, and untracked file contents. Resume refuses a changed
worktree. File evidence is a locator check and does not establish that a claim
is true; the adapter refuses to promote new decisions to verified.

The adapter can read and write local project context. It does not authenticate
the MCP client or coordinate concurrent writers to one JSONL store. Treat MCP
messages as data, keep the configured roots narrow, and use the adapter only
with clients you trust.

## Development checks

From a checkout that contains the adapter:

```sh
python test_mcp_bridge.py
python -B -m unittest -v test_reliability
python test_storage_security.py
```

The bridge tests use isolated temporary stores and repositories. A green test
suite does not establish live product-to-product use; the real client trial is
tracked in [issue #1](https://github.com/yunusarda-sudo/handoffstone/issues/1).
