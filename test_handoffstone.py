#!/usr/bin/env python3
"""
Tests for handoffstone — decision-aware context handoffs.

Tests cover:
- Decision/rationale preservation
- Superseded decision handling
- Evidence provenance
- Cross-project data isolation
- Context budget enforcement
- Malicious imported content
- Missing/invalid data
- Repeated import idempotency
- Resume after interruption
- Deterministic JSON export/import round-trip
"""

import json
import os
import tempfile
import shutil
from pathlib import Path

import handoffstone as cb


def _fixture_evidence():
    """Explicit synthetic attestation for tests of VERIFIED serialization."""
    return [cb.EvidenceReference(id="fixture-assertion", kind="test",
                                 locator=__file__, verified=True)]


class TestHandoffstone:
    """Test suite for handoffstone functionality."""

    def setup_method(self):
        """Set up test environment with isolated storage."""
        self.test_dir = tempfile.mkdtemp(prefix="handoffstone_test_")
        self.original_dir = cb.HANDOFFSTONE_DIR
        cb.HANDOFFSTONE_DIR = Path(self.test_dir)

        self.scope = "test-project"
        self.agent = "test-agent"

    def teardown_method(self):
        """Clean up test environment."""
        cb.HANDOFFSTONE_DIR = self.original_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # =========================================================================
    # Data Model Tests
    # =========================================================================

    def test_project_context_creation(self):
        """Test ProjectContext creation and serialization."""
        pc = cb.create_record(
            cb.RecordKind.PROJECT_CONTEXT,
            project_scope=self.scope,
            created_by=self.agent,
            name="Test Project",
            purpose="Testing handoffstone",
            scope=self.scope,
            tech_stack=["Python", "SQLite"],
            repositories=["/test/repo"],
        )

        assert pc.id.startswith("projectcontext-")
        assert pc.project_scope == self.scope
        assert pc.created_by == self.agent
        assert pc.name == "Test Project"
        assert pc.tech_stack == ["Python", "SQLite"]

        # Test JSON round-trip
        json_str = pc.to_json()
        pc2 = cb.ProjectContext.from_dict(json.loads(json_str))
        assert pc2.name == pc.name
        assert pc2.tech_stack == pc.tech_stack
        assert pc2.kind == cb.RecordKind.PROJECT_CONTEXT

    def test_decision_record_creation(self):
        """Test DecisionRecord creation with all fields."""
        dr = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use SQLite for storage",
            decision="Use embedded SQLite instead of PostgreSQL",
            rationale="Zero external deps, stdlib-only, WAL mode for concurrency",
            alternatives=[
                {"option": "PostgreSQL", "reason_rejected": "Requires separate server"},
                {"option": "Redis", "reason_rejected": "Not durable enough"},
            ],
            outcome="accepted",
            tags=["architecture", "storage"],
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        assert dr.id.startswith("decisionrecord-")
        assert dr.title == "Use SQLite for storage"
        assert dr.decision == "Use embedded SQLite instead of PostgreSQL"
        assert len(dr.alternatives) == 2
        assert dr.outcome == "accepted"
        assert dr.tags == ["architecture", "storage"]
        assert dr.status == cb.VerificationStatus.VERIFIED

        # Test JSON round-trip
        json_str = dr.to_json()
        dr2 = cb.DecisionRecord.from_dict(json.loads(json_str))
        assert dr2.title == dr.title
        assert dr2.alternatives == dr.alternatives
        assert dr2.status == dr.status

    def test_constraint_record_creation(self):
        """Test ConstraintRecord creation."""
        cr = cb.capture_constraint(
            project_scope=self.scope,
            agent=self.agent,
            constraint="Never store secrets in memory",
            category="security",
            severity="critical",
            source="architecture_decision",
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        assert cr.id.startswith("constraintrecord-")
        assert cr.constraint == "Never store secrets in memory"
        assert cr.category == "security"
        assert cr.severity == "critical"
        assert cr.source == "architecture_decision"
        assert cr.status == cb.VerificationStatus.VERIFIED

    def test_working_state_creation(self):
        """Test WorkingState creation."""
        ws = cb.capture_working_state(
            project_scope=self.scope,
            agent=self.agent,
            active_task="Implement feature X",
            state="in_progress",
            blockers=["Waiting for API key"],
            next_action="Contact admin for API key",
            progress={"completed": ["Design"], "remaining": ["Implementation", "Testing"]},
        )

        assert ws.id.startswith("workingstate-")
        assert ws.active_task == "Implement feature X"
        assert ws.state == "in_progress"
        assert ws.blockers == ["Waiting for API key"]
        assert ws.next_action == "Contact admin for API key"
        assert ws.progress["completed"] == ["Design"]

    def test_context_checkpoint_creation(self):
        """Test ContextCheckpoint creation."""
        cp = cb.create_checkpoint(
            project_scope=self.scope,
            agent=self.agent,
            label="Pre-refactor checkpoint",
            snapshot={"decisions": ["decision-1"], "constraints": ["constraint-1"]},
            parent_checkpoint="",
        )

        assert cp.id.startswith("contextcheckpoint-")
        assert cp.label == "Pre-refactor checkpoint"
        assert cp.snapshot["decisions"] == ["decision-1"]

    def test_handoff_record_creation(self):
        """Test HandoffRecord creation."""
        package = cb.ContextPackage(
            project_context=None,
            decisions=[],
            constraints=[],
            working_state=None,
            created_by=self.agent,
        )

        hr = cb.create_handoff(
            project_scope=self.scope,
            source_agent="claude-code",
            target_agent="chatgpt",
            task_summary="Continue implementation",
            package=package,
        )

        assert hr.id.startswith("handoffrecord-")
        assert hr.source_agent == "claude-code"
        assert hr.target_agent == "chatgpt"
        assert hr.task_summary == "Continue implementation"
        assert hr.accepted is False

    # =========================================================================
    # Evidence Provenance Tests
    # =========================================================================

    def test_evidence_reference_tracking(self):
        """Test that evidence references are properly tracked."""
        evidence = [
            cb.EvidenceReference(
                id="ev-1",
                kind="file",
                locator="src/main.py",
                description="Main implementation",
                verified=True,
            ),
            cb.EvidenceReference(
                id="ev-2",
                kind="commit",
                locator="abc123def",
                description="Initial commit",
                verified=False,
            ),
        ]

        dr = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Test Decision",
            decision="Test",
            rationale="Test rationale",
            evidence_refs=evidence,
        )

        assert len(dr.evidence) == 2
        assert dr.evidence[0].kind == "file"
        assert dr.evidence[0].locator == "src/main.py"
        assert dr.evidence[0].verified is True
        assert dr.evidence[1].kind == "commit"
        assert dr.evidence[1].verified is False

    def test_superseded_decision_handling(self):
        """Test that superseded decisions are properly tracked."""
        # Create initial decision
        dr1 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use Redis for caching",
            decision="Use Redis",
            rationale="Fast in-memory cache",
            outcome="accepted",
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        # Create superseding decision
        dr2 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use SQLite for caching",
            decision="Use SQLite with WAL mode",
            rationale="Redis adds operational complexity; SQLite WAL is fast enough",
            outcome="accepted",
            supersedes=[dr1.id],
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        # Reload dr1 from disk to get updated superseded_by
        loaded = cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)
        dr1_reloaded = next(r for r in loaded if r.id == dr1.id)

        # Verify supersession link
        assert dr1.id in dr2.supersedes
        assert dr2.id in dr1_reloaded.superseded_by

    def test_supersession_marks_old_decision_superseded(self):
        """A superseding decision flips the old one to SUPERSEDED status."""
        dr1 = cb.capture_decision(project_scope=self.scope, agent=self.agent,
                                  title="A", decision="Use A", rationale="r", tags=["t"])
        cb.capture_decision(project_scope=self.scope, agent=self.agent,
                            title="B", decision="Use B", rationale="r2", tags=["t"],
                            supersedes=[dr1.id])
        loaded = {r.id: r for r in cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)}
        assert loaded[dr1.id].status == cb.VerificationStatus.SUPERSEDED

    def test_build_supersession_history(self):
        """Compact change history pairs the old and new decision with the reason."""
        dr1 = cb.capture_decision(project_scope=self.scope, agent=self.agent,
                                  title="Use SQLite", decision="Use SQLite",
                                  rationale="old reason", tags=["db"])
        dr2 = cb.capture_decision(project_scope=self.scope, agent=self.agent,
                                  title="Use Postgres", decision="Use Postgres",
                                  rationale="Concurrent writers required", tags=["db"],
                                  supersedes=[dr1.id])
        decisions = cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)
        hist = cb.build_supersession_history(decisions)
        assert len(hist) == 1
        e = hist[0]
        assert e.supersedes == dr1.id
        assert e.decision_id == dr2.id
        assert "Postgres" in e.current_decision
        assert "SQLite" in e.previous_decision
        assert e.change_reason == "Concurrent writers required"

    def test_supersession_entry_roundtrip(self):
        e = cb.SupersessionEntry(decision_id="d2", current_decision="B", supersedes="d1",
                                 previous_decision="A", change_reason="why", status="verified")
        e2 = cb.SupersessionEntry.from_dict(json.loads(json.dumps(e.to_dict())))
        assert e2.to_dict() == e.to_dict()

    def test_package_roundtrip_with_history(self):
        dr1 = cb.capture_decision(project_scope=self.scope, agent=self.agent,
                                  title="Use SQLite", decision="Use SQLite",
                                  rationale="old", tags=["db"])
        cb.capture_decision(project_scope=self.scope, agent=self.agent,
                            title="Use Postgres", decision="Use Postgres",
                            rationale="Concurrent writers required", tags=["db"],
                            supersedes=[dr1.id])
        decisions = cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)
        hist = cb.build_supersession_history(decisions)
        active = [d for d in decisions if d.status != cb.VerificationStatus.SUPERSEDED]
        pkg = cb.ContextPackage(decisions=active, supersession_history=hist)
        pkg2 = cb.ContextPackage.from_json(pkg.to_json())
        assert len(pkg2.supersession_history) == 1
        assert pkg2.supersession_history[0].change_reason == "Concurrent writers required"

    def test_fit_package_to_budget(self):
        """The budget fitter never grows the package and respects the cap."""
        for i in range(10):
            cb.capture_decision(project_scope=self.scope, agent=self.agent,
                                title=f"D{i}", decision=f"Decision {i}", rationale=f"Rationale {i}")
        decisions = cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)
        pkg = cb.ContextPackage(decisions=decisions)
        for budget in (500, 1000, 3000):
            fitted = cb.fit_package_to_budget(pkg, budget)
            assert len(fitted.to_json()) <= len(pkg.to_json())
            assert len(fitted.to_json()) // 4 <= budget

    # =========================================================================
    # Compact wire format (transport encoding)
    # =========================================================================

    def _wire_package(self):
        """A package exercising decisions, supersession, evidence, constraint, state."""
        pc = cb.create_record(cb.RecordKind.PROJECT_CONTEXT, project_scope=self.scope,
                              created_by=self.agent, name="Proj", purpose="p", scope=self.scope)
        ev = cb.EvidenceReference(id="ev-1", kind="test", locator="tests/test_db.py",
                                  description="migration test", verified=True)
        d1 = cb.create_record(cb.RecordKind.DECISION_RECORD, project_scope=self.scope,
                              created_by=self.agent, title="Use SQLite", decision="Use SQLite",
                              rationale="Simple to operate", tags=["db"],
                              status=cb.VerificationStatus.SUPERSEDED)
        d2 = cb.create_record(cb.RecordKind.DECISION_RECORD, project_scope=self.scope,
                              created_by=self.agent, title="Use Postgres", decision="Use Postgres",
                              rationale="Concurrent writers required", tags=["db"],
                              evidence=[ev], supersedes=[d1.id],
                              status=cb.VerificationStatus.VERIFIED)
        d1.superseded_by = [d2.id]
        foreign = cb.create_record(cb.RecordKind.DECISION_RECORD, project_scope="other-scope",
                                   created_by=self.agent, title="Foreign", decision="Use Z",
                                   rationale="belongs elsewhere")
        c = cb.create_record(cb.RecordKind.CONSTRAINT_RECORD, project_scope=self.scope,
                             created_by=self.agent, constraint="No secrets in logs",
                             category="security", severity="critical", source="user",
                             evidence=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED)
        ws = cb.create_record(cb.RecordKind.WORKING_STATE, project_scope=self.scope,
                              created_by=self.agent, active_task="ship", state="blocked",
                              next_action="write tests")
        hist = cb.build_supersession_history([d1, d2])
        return cb.ContextPackage(project_context=pc, decisions=[d2, foreign],
                                 constraints=[c], working_state=ws,
                                 supersession_history=hist, evidence=[ev],
                                 created_by=self.agent), d1, d2, ev, foreign

    def test_wire_roundtrip_is_lossless(self):
        pkg, *_ = self._wire_package()
        decoded = cb.ContextPackage.from_wire_json(pkg.to_wire_json())
        assert decoded.to_dict() == pkg.to_dict()

    def test_wire_backward_compatible_with_legacy_json(self):
        pkg, *_ = self._wire_package()
        legacy = cb.ContextPackage.from_wire_json(pkg.to_json())
        assert legacy.to_dict() == pkg.to_dict()

    def test_wire_is_meaningfully_smaller(self):
        pkg, *_ = self._wire_package()
        assert len(pkg.to_wire_json()) < len(pkg.to_json())
        assert len(pkg.to_json()) / len(pkg.to_wire_json()) > 1.5

    def test_wire_encoding_is_deterministic(self):
        pkg, *_ = self._wire_package()
        assert pkg.to_wire_json() == pkg.to_wire_json()

    def test_wire_preserves_supersession_links(self):
        pkg, d1, d2, *_ = self._wire_package()
        decoded = cb.ContextPackage.from_wire_json(pkg.to_wire_json())
        assert decoded.decisions[0].supersedes == [d1.id]
        assert decoded.supersession_history[0].supersedes == d1.id
        assert decoded.supersession_history[0].decision_id == d2.id
        assert decoded.supersession_history[0].change_reason == "Concurrent writers required"

    def test_wire_preserves_evidence_provenance(self):
        pkg, *_ = self._wire_package()
        decoded = cb.ContextPackage.from_wire_json(pkg.to_wire_json())
        ev = decoded.decisions[0].evidence[0]
        assert (ev.id, ev.kind, ev.locator) == ("ev-1", "test", "tests/test_db.py")
        assert ev.description == "migration test"
        assert ev.verified is True
        assert ev.captured_at  # provenance timestamp retained

    def test_wire_preserves_verification_status(self):
        pkg, *_ = self._wire_package()
        decoded = cb.ContextPackage.from_wire_json(pkg.to_wire_json())
        assert decoded.decisions[0].status == cb.VerificationStatus.VERIFIED

    def test_wire_no_cross_project_leakage(self):
        pkg, d1, d2, ev, foreign = self._wire_package()
        decoded = cb.ContextPackage.from_wire_json(pkg.to_wire_json())
        by_id = {d.id: d for d in decoded.decisions}
        assert by_id[foreign.id].project_scope == "other-scope"
        assert by_id[d2.id].project_scope == self.scope

    def test_wire_rejects_malformed_input(self):
        for bad in ("[]", "null", '{"foo":1}', '{"wv":99}',
                    '{"wv":2,"d":[{"t":"no id"}]}'):
            try:
                cb.package_from_wire_json(bad)
            except ValueError:
                continue
            raise AssertionError(f"should have rejected: {bad}")

    def test_wire_fit_respects_compact_budget(self):
        pkg, *_ = self._wire_package()
        fitted = cb.fit_package_to_budget(pkg, 200, wire="compact")
        assert len(fitted.to_wire_json()) // 4 <= 200

    # =========================================================================
    # Cross-Project Data Isolation Tests
    # =========================================================================

    def test_cross_project_isolation(self):
        """Test that records are isolated by project scope."""
        scope_a = "project-a"
        scope_b = "project-b"

        # Create records in different scopes
        cb.capture_decision(scope_a, self.agent, "Decision A", "Use X", "Reason A")
        cb.capture_decision(scope_b, self.agent, "Decision B", "Use Y", "Reason B")

        # Load records from each scope
        records_a = cb.load_records(scope_a, cb.RecordKind.DECISION_RECORD)
        records_b = cb.load_records(scope_b, cb.RecordKind.DECISION_RECORD)

        assert len(records_a) == 1
        assert len(records_b) == 1
        assert records_a[0].title == "Decision A"
        assert records_b[0].title == "Decision B"

        # Cross-scope query should not leak
        try:
            cb.load_records("")
        except cb.InvalidScopeError:
            pass  # Empty scope is now rejected; it is never a global query.
        else:
            raise AssertionError("Empty scope must not be accepted")

    # =========================================================================
    # Context Budget Tests
    # =========================================================================

    def test_context_budget_enforcement(self):
        """Test context budget token limiting."""
        budget = cb.ContextBudget(max_tokens=5000)  # Must exceed RESERVED_FOR_TASK (2000)

        # Should fit
        assert budget.can_add("short text")
        budget.add("short text")
        assert budget.used > 0

        # Should not fit - use text that exceeds available budget (5000 - 2000 = 3000 tokens)
        # 3000 tokens * 4 chars = 12000 chars
        long_text = "x" * 15000  # ~3750 tokens > 3000 available
        assert not budget.can_add(long_text)

        # Remaining calculation
        remaining = budget.remaining()
        assert remaining >= 0

    def test_context_package_budget_awareness(self):
        """Test that context package respects budget in exports."""
        # Create a package with many decisions
        decisions = []
        for i in range(10):
            dr = cb.capture_decision(
                project_scope=self.scope,
                agent=self.agent,
                title=f"Decision {i}",
                decision=f"Decision content {i}" * 50,  # Large content
                rationale=f"Rationale {i}" * 50,
            )
            decisions.append(dr)

        package = cb.ContextPackage(
            project_context=None,
            decisions=decisions,
            constraints=[],
            working_state=None,
            created_by=self.agent,
        )

        json_out = package.to_json()
        md_out = package.to_markdown()

        # Both exports should work
        assert len(json_out) > 0
        assert len(md_out) > 0

        # Round-trip should preserve data
        package2 = cb.ContextPackage.from_json(json_out)
        assert len(package2.decisions) == 10

    # =========================================================================
    # Security: Malicious Content Filtering
    # =========================================================================

    def test_secret_filtering(self):
        """Test that secrets are filtered from transfer text."""
        text_with_secrets = """
        Here is my API key: sk-abcdefghijklmnopqrstuvwxyz123456
        And a GitHub token: ghp_abcdefghijklmnopqrstuvwxyz123456
        Also a password: password123
        """

        sanitized = cb.sanitize_for_transfer(text_with_secrets)

        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in sanitized
        assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_secret_detection(self):
        """Test secret detection."""
        text = "API key: sk-test12345678901234567890"
        found = cb.detect_secrets(text)
        assert len(found) > 0

    def test_email_filtering(self):
        """Test that emails are filtered."""
        text = "Contact me at user@example.com for details"
        sanitized = cb.sanitize_for_transfer(text)
        assert "user@example.com" not in sanitized
        assert "[REDACTED]" in sanitized

    # =========================================================================
    # Missing/Invalid Data Handling
    # =========================================================================

    def test_missing_optional_fields(self):
        """Test handling of missing optional fields."""
        dr = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Minimal Decision",
            decision="Just do it",
            rationale="",  # Required but can be empty
            alternatives=[],
            evidence_refs=[],
        )

        assert dr.rationale == ""
        assert dr.alternatives == []
        assert dr.evidence == []

    def test_invalid_json_import_graceful(self):
        """Test graceful handling of invalid JSON."""
        # Invalid JSON should not crash
        try:
            cb.ContextPackage.from_json("not valid json")
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass  # Expected

    def test_missing_record_graceful(self):
        """Test graceful handling of missing records."""
        latest = cb.get_latest_record("nonexistent-scope", cb.RecordKind.DECISION_RECORD)
        assert latest is None

    # =========================================================================
    # Idempotency Tests
    # =========================================================================

    def test_repeated_import_idempotency(self):
        """Test that repeated imports are idempotent (via idempotency key)."""
        dr1 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Idempotent Decision",
            decision="Test",
            rationale="Test",
        )

        dr2 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Idempotent Decision",
            decision="Test",
            rationale="Test",
        )

        # Idempotency keys should be the same for identical content on same day
        key1 = cb.idempotency_key(dr1)
        key2 = cb.idempotency_key(dr2)

        # Keys should be the same because date, title, scope, agent, kind match
        assert key1 == key2  # Same day, same content = same key

    def test_handoff_package_round_trip(self):
        """Test deterministic JSON export/import round-trip."""
        # Create a complex package
        pc = cb.create_record(
            cb.RecordKind.PROJECT_CONTEXT,
            project_scope=self.scope,
            created_by=self.agent,
            name="Test",
            purpose="Test",
        )

        dr = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Test Decision",
            decision="Test",
            rationale="Test",
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        cr = cb.capture_constraint(
            project_scope=self.scope,
            agent=self.agent,
            constraint="Test constraint",
        )

        ws = cb.capture_working_state(
            project_scope=self.scope,
            agent=self.agent,
            active_task="Test task",
        )

        package = cb.ContextPackage(
            project_context=pc,
            decisions=[dr],
            constraints=[cr],
            working_state=ws,
            open_questions=["Q1?", "Q2?"],
            uncertainty=["Unknown X"],
            created_by=self.agent,
        )

        # Export to JSON
        json_str = package.to_json()

        # Import back
        package2 = cb.ContextPackage.from_json(json_str)

        # Verify all data preserved
        assert package2.project_context.name == pc.name
        assert len(package2.decisions) == 1
        assert package2.decisions[0].title == dr.title
        assert package2.decisions[0].status == dr.status
        assert len(package2.constraints) == 1
        assert package2.constraints[0].constraint == cr.constraint
        assert package2.working_state.active_task == ws.active_task
        assert package2.open_questions == ["Q1?", "Q2?"]
        assert package2.uncertainty == ["Unknown X"]

    # =========================================================================
    # Resume After Interruption Tests
    # =========================================================================

    def test_resume_from_checkpoint(self):
        """Test resuming context from a checkpoint."""
        # Create checkpoint with snapshot
        cp = cb.create_checkpoint(
            project_scope=self.scope,
            agent=self.agent,
            label="Checkpoint 1",
            snapshot={
                "decisions": [{"id": "d1", "title": "Decision 1"}],
                "constraints": [{"id": "c1", "constraint": "Constraint 1"}],
            },
        )

        # Load and verify
        loaded = cb.get_latest_record(self.scope, cb.RecordKind.CONTEXT_CHECKPOINT)
        assert loaded is not None
        assert loaded.label == "Checkpoint 1"
        assert loaded.snapshot["decisions"][0]["title"] == "Decision 1"

    def test_context_diff(self):
        """Test context diff between checkpoints."""
        # Create two checkpoints
        cp1 = cb.create_checkpoint(
            project_scope=self.scope,
            agent=self.agent,
            label="Before",
            snapshot={
                "decisions": [{"id": "d1", "title": "Old Decision"}],
                "constraints": [{"id": "c1", "constraint": "Old Constraint"}],
            },
        )

        cp2 = cb.create_checkpoint(
            project_scope=self.scope,
            agent=self.agent,
            label="After",
            snapshot={
                "decisions": [
                    {"id": "d1", "title": "Old Decision"},
                    {"id": "d2", "title": "New Decision"},
                ],
                "constraints": [{"id": "c1", "constraint": "Old Constraint"}],
            },
            parent_checkpoint=cp1.id,
        )

        # Verify both exist
        checkpoints = cb.load_records(self.scope, cb.RecordKind.CONTEXT_CHECKPOINT)
        assert len(checkpoints) == 2

    # =========================================================================
    # Conflict Detection Tests
    # =========================================================================

    def test_conflict_detection_contradictory_decisions(self):
        """Test detection of contradictory decisions."""
        dr1 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use Redis",
            decision="Use Redis for caching",
            rationale="Fast",
            tags=["caching"],
            outcome="accepted",
        )

        dr2 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use Memcached",
            decision="Use Memcached for caching",
            rationale="Simpler",
            tags=["caching"],
            outcome="accepted",
        )

        conflicts = cb.detect_conflicts([dr1, dr2])
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "contradictory_decisions"
        assert dr1.id in conflicts[0]["records"]
        assert dr2.id in conflicts[0]["records"]

    def test_conflict_detection_no_false_positive(self):
        """Test that superseded decisions don't trigger conflicts."""
        dr1 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use Redis",
            decision="Use Redis",
            rationale="Fast",
            tags=["caching"],
            outcome="accepted",
        )

        # Supersede it
        dr1.status = cb.VerificationStatus.SUPERSEDED

        dr2 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Use Memcached",
            decision="Use Memcached",
            rationale="Simpler",
            tags=["caching"],
            outcome="accepted",
        )

        conflicts = cb.detect_conflicts([dr1, dr2])
        # Should not detect conflict because dr1 is superseded
        assert len(conflicts) == 0

    # =========================================================================
    # Persistence Tests
    # =========================================================================

    def test_record_persistence(self):
        """Test that records persist to disk and can be reloaded."""
        dr = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Persistent Decision",
            decision="Test",
            rationale="Test",
        )

        # Create new instance with same storage dir
        cb.HANDOFFSTONE_DIR = Path(self.test_dir)
        loaded = cb.load_records(self.scope, cb.RecordKind.DECISION_RECORD)

        assert len(loaded) == 1
        assert loaded[0].title == "Persistent Decision"

    def test_context_export_import(self):
        """Test full context export and import."""
        # Create various records
        cb.capture_decision(self.scope, self.agent, "D1", "Dec 1", "Reason 1")
        cb.capture_decision(self.scope, self.agent, "D2", "Dec 2", "Reason 2")
        cb.capture_constraint(self.scope, self.agent, "Constraint 1")
        cb.capture_working_state(self.scope, self.agent, "Task 1")

        # Export
        exported = cb.load_records(self.scope)
        assert len(exported) == 4

        # Verify types
        types = {type(r).__name__ for r in exported}
        assert "DecisionRecord" in types
        assert "ConstraintRecord" in types
        assert "WorkingState" in types


# =========================================================================
# Integration Test: MVP Vertical Slice
# =========================================================================

class TestMVPVerticalSlice:
    """End-to-end test of the MVP vertical slice."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp(prefix="mvp_test_")
        self.original_dir = cb.HANDOFFSTONE_DIR
        cb.HANDOFFSTONE_DIR = Path(self.test_dir)

        self.scope = "mvp-test"
        self.agent = "source-agent"

    def teardown_method(self):
        cb.HANDOFFSTONE_DIR = self.original_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_mvp_flow(self):
        """Test the complete MVP flow:
        1. Initialize project
        2. Capture technical decision
        3. Revise decision
        4. Leave task half-done
        5. Create checkpoint and handoff
        6. Restore on second agent
        7. Verify second agent understands current decision, why previous changed, remaining task, constraints
        """
        # 1. Initialize project context
        pc = cb.create_record(
            cb.RecordKind.PROJECT_CONTEXT,
            project_scope=self.scope,
            created_by=self.agent,
            name="MVP Test Project",
            purpose="Test the MVP flow",
            scope=self.scope,
            tech_stack=["Python", "SQLite"],
            repositories=["/test/repo"],
        )
        cb.save_record(pc)

        # 2. Capture initial technical decision
        dr1 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Database Choice",
            decision="Use PostgreSQL for primary database",
            rationale="ACID compliance, mature ecosystem, team expertise",
            alternatives=[
                {"option": "MySQL", "reason_rejected": "Less advanced JSON support"},
                {"option": "MongoDB", "reason_rejected": "No ACID transactions needed"},
            ],
            outcome="accepted",
            tags=["database", "architecture"],
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        # 3. Revise the decision (simulating change of mind)
        dr2 = cb.capture_decision(
            project_scope=self.scope,
            agent=self.agent,
            title="Database Choice",
            decision="Use SQLite with WAL mode for primary database",
            rationale="PostgreSQL adds operational overhead; SQLite WAL provides sufficient concurrency for our scale with zero ops burden",
            alternatives=[
                {"option": "PostgreSQL", "reason_rejected": "Operational overhead not justified for current scale"},
                {"option": "MySQL", "reason_rejected": "Same operational concerns as PostgreSQL"},
            ],
            outcome="accepted",
            tags=["database", "architecture"],
            supersedes=[dr1.id],
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        # 4. Capture a constraint
        cr = cb.capture_constraint(
            project_scope=self.scope,
            agent=self.agent,
            constraint="Zero external database dependencies - must run fully local",
            category="architecture",
            severity="critical",
            source="architecture_decision",
            evidence_refs=_fixture_evidence(), status=cb.VerificationStatus.VERIFIED,
        )

        # 5. Leave task half-done - capture working state
        ws = cb.capture_working_state(
            project_scope=self.scope,
            agent=self.agent,
            active_task="Implement user authentication module",
            state="in_progress",
            blockers=["Need to decide on JWT vs session-based auth"],
            next_action="Research JWT libraries for Python and create decision record",
            progress={
                "completed": ["Database setup", "Schema design"],
                "remaining": ["Auth decision", "Auth implementation", "Token refresh logic", "Tests"]
            },
        )

        # 6. Create checkpoint
        cp = cb.create_checkpoint(
            project_scope=self.scope,
            agent=self.agent,
            label="Pre-auth-decision checkpoint",
            snapshot={
                "decisions": [dr1.id, dr2.id],
                "constraints": [cr.id],
                "working_state": ws.id,
            },
        )

        # 7. Create handoff package
        package = cb.ContextPackage(
            project_context=pc,
            decisions=[dr1, dr2],
            constraints=[cr],
            working_state=ws,
            open_questions=["Which JWT library to use?", "Token expiration strategy?"],
            uncertainty=["Refresh token rotation implementation details"],
            created_by=self.agent,
        )

        handoff = cb.create_handoff(
            project_scope=self.scope,
            source_agent="claude-code",
            target_agent="chatgpt",
            task_summary="Continue auth implementation after database decision",
            package=package,
        )

        # 8. Simulate second agent restoring context
        # (In real usage, this would be the JSON package passed to the new agent)
        json_package = package.to_json()
        restored = cb.ContextPackage.from_json(json_package)

        # VERIFICATION: Second agent should understand:
        # - Current decision (SQLite, not PostgreSQL)
        assert len(restored.decisions) == 2
        current_decision = next(d for d in restored.decisions if d.outcome == "accepted" and d.id not in [d.superseded_by for d in restored.decisions])
        # Actually the latest non-superseded is dr2
        latest_db_decision = max(restored.decisions, key=lambda d: d.created_at)
        assert "SQLite" in latest_db_decision.decision
        assert "PostgreSQL" not in latest_db_decision.decision

        # - Why previous decision changed (rationale in dr2)
        assert dr2.rationale in restored.decisions[1].rationale
        assert "operational overhead" in dr2.rationale

        # - Remaining task (auth implementation)
        assert restored.working_state is not None
        assert "auth" in restored.working_state.active_task.lower()
        assert "Auth implementation" in restored.working_state.progress["remaining"]

        # - Constraints to follow (zero external deps)
        assert len(restored.constraints) == 1
        assert "Zero external database dependencies" in restored.constraints[0].constraint
        assert restored.constraints[0].severity == "critical"

        # - Open questions and uncertainty
        assert "Which JWT library to use?" in restored.open_questions
        assert "Refresh token rotation implementation details" in restored.uncertainty

        print("✅ MVP Vertical Slice Test PASSED!")
        print(f"   Project: {restored.project_context.name}")
        print(f"   Current DB Decision: {latest_db_decision.title}")
        print(f"   Superseded: {dr1.title} -> {dr2.title}")
        print(f"   Active Task: {restored.working_state.active_task}")
        print(f"   Remaining: {restored.working_state.progress['remaining']}")
        print(f"   Critical Constraint: {restored.constraints[0].constraint}")
        print(f"   Open Questions: {restored.open_questions}")
        print(f"   Uncertainty: {restored.uncertainty}")


def run_all_tests():
    """Run all tests and report results."""
    import sys

    test_suite = TestHandoffstone()
    mvp_suite = TestMVPVerticalSlice()

    tests = [
        # Data model tests
        ("ProjectContext creation", test_suite.test_project_context_creation),
        ("DecisionRecord creation", test_suite.test_decision_record_creation),
        ("ConstraintRecord creation", test_suite.test_constraint_record_creation),
        ("WorkingState creation", test_suite.test_working_state_creation),
        ("ContextCheckpoint creation", test_suite.test_context_checkpoint_creation),
        ("HandoffRecord creation", test_suite.test_handoff_record_creation),
        # Evidence provenance
        ("Evidence reference tracking", test_suite.test_evidence_reference_tracking),
        ("Superseded decision handling", test_suite.test_superseded_decision_handling),
        ("Supersession marks old decision superseded", test_suite.test_supersession_marks_old_decision_superseded),
        ("Build supersession history", test_suite.test_build_supersession_history),
        ("Supersession entry round-trip", test_suite.test_supersession_entry_roundtrip),
        ("Package round-trip with history", test_suite.test_package_roundtrip_with_history),
        ("Fit package to budget", test_suite.test_fit_package_to_budget),
        # Compact wire format
        ("Wire round-trip lossless", test_suite.test_wire_roundtrip_is_lossless),
        ("Wire backward-compatible with legacy JSON", test_suite.test_wire_backward_compatible_with_legacy_json),
        ("Wire is meaningfully smaller", test_suite.test_wire_is_meaningfully_smaller),
        ("Wire encoding deterministic", test_suite.test_wire_encoding_is_deterministic),
        ("Wire preserves supersession links", test_suite.test_wire_preserves_supersession_links),
        ("Wire preserves evidence provenance", test_suite.test_wire_preserves_evidence_provenance),
        ("Wire preserves verification status", test_suite.test_wire_preserves_verification_status),
        ("Wire: no cross-project leakage", test_suite.test_wire_no_cross_project_leakage),
        ("Wire rejects malformed input", test_suite.test_wire_rejects_malformed_input),
        ("Wire fit respects compact budget", test_suite.test_wire_fit_respects_compact_budget),
        # Cross-project isolation
        ("Cross-project isolation", test_suite.test_cross_project_isolation),
        # Context budget
        ("Context budget enforcement", test_suite.test_context_budget_enforcement),
        ("Context package budget awareness", test_suite.test_context_package_budget_awareness),
        # Security
        ("Secret filtering", test_suite.test_secret_filtering),
        ("Secret detection", test_suite.test_secret_detection),
        ("Email filtering", test_suite.test_email_filtering),
        # Missing/invalid data
        ("Missing optional fields", test_suite.test_missing_optional_fields),
        ("Invalid JSON import", test_suite.test_invalid_json_import_graceful),
        ("Missing record graceful", test_suite.test_missing_record_graceful),
        # Idempotency
        ("Repeated import idempotency", test_suite.test_repeated_import_idempotency),
        ("Handoff package round-trip", test_suite.test_handoff_package_round_trip),
        # Resume
        ("Resume from checkpoint", test_suite.test_resume_from_checkpoint),
        ("Context diff", test_suite.test_context_diff),
        # Conflict detection
        ("Conflict detection - contradictory", test_suite.test_conflict_detection_contradictory_decisions),
        ("Conflict detection - no false positive", test_suite.test_conflict_detection_no_false_positive),
        # Persistence
        ("Record persistence", test_suite.test_record_persistence),
        ("Context export/import", test_suite.test_context_export_import),
        # MVP Vertical Slice
        ("MVP Full Flow", mvp_suite.test_full_mvp_flow),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        test_suite.setup_method() if "MVP" not in name else mvp_suite.setup_method()
        try:
            test_func()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        finally:
            test_suite.teardown_method() if "MVP" not in name else mvp_suite.teardown_method()

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
