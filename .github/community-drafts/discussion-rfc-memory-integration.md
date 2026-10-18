# RFC: How should Handoffstone integrate with existing agent memory systems?

## Context

`handoffstone` is a standalone, stdlib-only package for portable, verifiable,
decision-aware context handoffs. A local project currently keeps its **own
copy** of the same code under the name `context_bridge`, storing records at
`~/.mem0/context_bridge`, while the package stores at `~/.handoffstone`
(`HANDOFFSTONE_HOME`). The two copies have started to drift.

## Problem

We want the standalone package to become the single source of truth, without:

- silently moving a user's existing data to a new path, or
- breaking existing CLI/MCP callers that `import context_bridge`.

## Questions for the community

1. Integration shape: a thin `context_bridge` compatibility shim that
   re-exports `handoffstone`, or migrate callers to `import handoffstone` outright?
2. Storage continuity: keep `~/.mem0/context_bridge` (via `HANDOFFSTONE_HOME`),
   migrate with an explicit opt-in tool, or something else?
3. Dependency strategy before a PyPI release: editable local path, vendored
   copy, or pinned release?
4. Are there better architectural patterns for multi-agent memory we are missing?

## Out of scope

This is a design discussion, not a bug. Concrete, actionable follow-ups that
come out of it should be filed as separate Issues.
