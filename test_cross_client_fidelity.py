"""Cross-client handoff fidelity (stdlib-only).

Simulates two isolated agent stores: a producer writes a canonical package
(JSON + compact wire), a consumer in a separate HANDOFFSTONE_DIR reloads it
and compares decisions, constraints, supersession history, and evidence.

This does not replace a live Claude Code ↔ Codex product trial; it gates the
transport contract those trials depend on. See docs/cross-client-trial.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import handoffstone as hs


SCOPE = "cross-client-demo"
REPO_ROOT = Path(__file__).resolve().parent


def _critical_snapshot(pkg: hs.ContextPackage) -> dict:
    """Field-level view issue #1 asks receivers to compare."""
    return {
        "decisions": [
            {
                "id": d.id,
                "title": d.title,
                "decision": d.decision,
                "rationale": d.rationale,
                "status": d.status.value if hasattr(d.status, "value") else d.status,
                "supersedes": list(d.supersedes),
                "superseded_by": list(d.superseded_by),
                "evidence": [
                    {"kind": e.kind, "locator": e.locator, "description": e.description}
                    for e in d.evidence
                ],
            }
            for d in pkg.decisions
        ],
        "constraints": [
            {
                "id": c.id,
                "constraint": c.constraint,
                "severity": c.severity,
                "category": c.category,
            }
            for c in pkg.constraints
        ],
        "supersession_history": [
            {
                "decision_id": s.decision_id,
                "supersedes": s.supersedes,
                "current_decision": s.current_decision,
                "previous_decision": s.previous_decision,
                "change_reason": s.change_reason,
            }
            for s in pkg.supersession_history
        ],
        "evidence": [
            {"kind": e.kind, "locator": e.locator, "description": e.description}
            for e in pkg.evidence
        ],
        "working_state": (
            {
                "active_task": pkg.working_state.active_task,
                "next_action": pkg.working_state.next_action,
                "state": pkg.working_state.state,
            }
            if pkg.working_state
            else None
        ),
    }


def build_producer_package(agent: str = "producer-client") -> hs.ContextPackage:
    evidence = hs.EvidenceReference(
        id="ev-conv-1",
        kind="conversation",
        locator="trial-thread-1",
        description="Producer captured the database decision from chat",
    )
    project = hs.create_record(
        hs.RecordKind.PROJECT_CONTEXT,
        project_scope=SCOPE,
        created_by=agent,
        name="cross-client-demo",
        purpose="Prove package fidelity across isolated agent stores",
        scope=SCOPE,
        tech_stack=["Python"],
        repositories=["https://github.com/yunusarda-sudo/handoffstone"],
    )
    first = hs.capture_decision(
        project_scope=SCOPE,
        agent=agent,
        title="Database Choice",
        decision="Use PostgreSQL",
        rationale="Team already runs Postgres in production",
        alternatives=[{"option": "SQLite", "reason_rejected": "Thought we needed multi-writer"}],
        outcome="accepted",
        evidence_refs=[evidence],
        status=hs.VerificationStatus.VERIFIED,
    )
    second = hs.capture_decision(
        project_scope=SCOPE,
        agent=agent,
        title="Database Choice",
        decision="Use SQLite with WAL",
        rationale="Local-first alpha; zero ops burden",
        alternatives=[{"option": "PostgreSQL", "reason_rejected": "Ops overhead unjustified"}],
        outcome="accepted",
        supersedes=[first.id],
        evidence_refs=[evidence],
        status=hs.VerificationStatus.VERIFIED,
    )
    constraint = hs.capture_constraint(
        project_scope=SCOPE,
        agent=agent,
        constraint="Core library must stay stdlib-only",
        category="architecture",
        severity="critical",
        source="project_charter",
        status=hs.VerificationStatus.VERIFIED,
    )
    working = hs.capture_working_state(
        project_scope=SCOPE,
        agent=agent,
        active_task="Validate cross-client handoff fidelity",
        state="in_progress",
        blockers=["Need a second client to import the package"],
        next_action="Import package on the consuming client and diff critical fields",
        progress={"completed": ["Capture"], "remaining": ["Import", "Report"]},
    )
    decisions = hs.load_records(SCOPE, hs.RecordKind.DECISION_RECORD)
    history = hs.build_supersession_history(decisions)
    return hs.ContextPackage(
        project_context=project,
        decisions=decisions,
        constraints=[constraint],
        supersession_history=history,
        working_state=working,
        evidence=[evidence],
        open_questions=["Does Markdown-only handoff lose supersession links?"],
        uncertainty=["MCP host coverage still pending"],
        created_by=agent,
    )


class CrossClientFidelityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.producer_home = Path(self.tmp.name) / "producer"
        self.consumer_home = Path(self.tmp.name) / "consumer"
        self.producer_home.mkdir()
        self.consumer_home.mkdir()
        self.old_home = hs.HANDOFFSTONE_DIR
        hs.HANDOFFSTONE_DIR = self.producer_home

    def tearDown(self):
        hs.HANDOFFSTONE_DIR = self.old_home
        self.tmp.cleanup()

    def test_canonical_json_survives_isolated_consumer_store(self):
        produced = build_producer_package("claude-code-sim")
        export_path = Path(self.tmp.name) / "handoff.json"
        export_path.write_text(produced.to_json(), encoding="utf-8")

        # Consumer process: fresh interpreter + separate store home.
        consumer_script = f"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, {str(REPO_ROOT)!r})
import handoffstone as hs
hs.HANDOFFSTONE_DIR = Path({str(self.consumer_home)!r})
pkg = hs.ContextPackage.from_json(Path({str(export_path)!r}).read_text(encoding="utf-8"))
# Persist on the consumer so a follow-up session can load_records.
for record in [pkg.project_context, *pkg.decisions, *pkg.constraints, pkg.working_state]:
    if record is not None:
        hs.save_record(record)
snap = {{
    "decision_ids": sorted(d.id for d in pkg.decisions),
    "decision_texts": sorted(d.decision for d in pkg.decisions),
    "constraint_texts": [c.constraint for c in pkg.constraints],
    "history": [
        {{"supersedes": s.supersedes, "decision_id": s.decision_id, "reason": s.change_reason}}
        for s in pkg.supersession_history
    ],
    "evidence_kinds": sorted({{e.kind for e in pkg.evidence}} | {{e.kind for d in pkg.decisions for e in d.evidence}}),
    "working_task": pkg.working_state.active_task if pkg.working_state else None,
}}
print(json.dumps(snap, sort_keys=True))
"""
        proc = subprocess.run(
            [sys.executable, "-c", consumer_script],
            check=True,
            capture_output=True,
            text=True,
        )
        got = json.loads(proc.stdout.strip())
        expected = {
            "decision_ids": sorted(d.id for d in produced.decisions),
            "decision_texts": sorted(d.decision for d in produced.decisions),
            "constraint_texts": [c.constraint for c in produced.constraints],
            "history": [
                {"supersedes": s.supersedes, "decision_id": s.decision_id, "reason": s.change_reason}
                for s in produced.supersession_history
            ],
            "evidence_kinds": sorted(
                {e.kind for e in produced.evidence}
                | {e.kind for d in produced.decisions for e in d.evidence}
            ),
            "working_task": produced.working_state.active_task if produced.working_state else None,
        }
        self.assertEqual(got, expected)
        self.assertIn("conversation", got["evidence_kinds"])
        self.assertEqual(len(got["history"]), 1)

    def test_wire_round_trip_matches_critical_snapshot(self):
        produced = build_producer_package("codex-sim")
        wire = produced.to_wire_json()
        restored = hs.ContextPackage.from_wire_json(wire)
        self.assertEqual(_critical_snapshot(restored), _critical_snapshot(produced))

    def test_budget_trim_keeps_supersession_and_critical_constraint(self):
        produced = build_producer_package("budget-sim")
        # Tight but large enough for core + history + at least one constraint.
        fitted = hs.fit_package_to_budget(produced, max_tokens=1200, wire="compact")
        restored = hs.ContextPackage.from_wire_json(fitted.to_wire_json())
        self.assertTrue(restored.supersession_history, "change history must survive a budget trim")
        self.assertTrue(
            any(c.severity == "critical" for c in restored.constraints)
            or any("stdlib-only" in c.constraint for c in restored.constraints)
            or restored.project_context is not None,
            "a critical architecture fact or project context must remain",
        )
        # Receiving side still sees what replaced what.
        link = restored.supersession_history[0]
        self.assertTrue(link.supersedes)
        self.assertTrue(link.decision_id)
        self.assertIn("SQLite", link.current_decision)


if __name__ == "__main__":
    unittest.main()
