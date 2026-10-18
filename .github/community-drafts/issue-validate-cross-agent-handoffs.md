---
labels: help wanted, testing
---

# Validate handoffs across real AI agent clients

## Why

Current evidence comes from a single, scripted evaluation loop
(`bench_handoffstone.py`). Passing there does **not** prove a handoff survives a
real move between *different* agent clients — we should not generalize
single-model results.

## Goal

Demonstrate (or falsify) that a `handoffstone` package exported by one agent
client can be consumed by another with no loss of decisions, rationale,
constraints, change history, or evidence provenance.

## Tasks

- [ ] Claude Code -> Codex (and vice versa): export from one, import on the other, diff every field.
- [ ] At least one MCP client (a host using the `context_handoff` tool).
- [ ] Round-trip fidelity: identical `decisions` / `constraints` / `change_history` / `evidence` after export -> import.
- [ ] A budget-trimmed package still preserves critical facts on the receiving side.
- [ ] Report exact commands, client versions, and any observed diffs.

## Acceptance criteria

- Reproducible script/instructions plus a short result report (what matched, what did not).
- Any failure documented with the raw package JSON that caused it.

## How to run

```bash
python3 handoffstone.py        # smoke
python3 test_handoffstone.py   # core tests
```
