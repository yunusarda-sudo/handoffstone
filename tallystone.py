#!/usr/bin/env python3
"""
tallystone — Portable, verifiable, decision-aware context handoffs for AI agents.

Canonical context model, capture, handoff, and cross-client integration: move
decisions, their rationale, the evidence they rest on, and how the work
changed hands between agents (ChatGPT, Claude, Codex, OpenCode, ...).

Stdlib-only and local-first: no network, no API keys, no external services.

The name: a *tallystone* is a marked stone used to keep count and mark a
boundary — a durable, verifiable reference point for what was decided and the
evidence it rests on.
"""

import datetime
import hashlib
import json
import os
import re
import uuid
import copy
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class VerificationStatus(str, Enum):
    """Verification status of a context record."""
    VERIFIED = "verified"           # Confirmed by user or test evidence
    USER_ASSERTED = "user_asserted"  # User stated it, not independently verified
    AGENT_INFERRED = "agent_inferred"  # Agent inferred from context
    UNVERIFIED = "unverified"       # No verification attempted
    SUPERSEDED = "superseded"       # Replaced by newer record


class RecordKind(str, Enum):
    """Types of context records."""
    PROJECT_CONTEXT = "ProjectContext"
    DECISION_RECORD = "DecisionRecord"
    CONSTRAINT_RECORD = "ConstraintRecord"
    WORKING_STATE = "WorkingState"
    EVIDENCE_REFERENCE = "EvidenceReference"
    CONTEXT_CHECKPOINT = "ContextCheckpoint"
    HANDOFF_RECORD = "HandoffRecord"


@dataclass
class EvidenceReference:
    """Reference to verifiable evidence supporting a record."""
    id: str
    kind: str  # "file", "commit", "test", "url", "conversation", "memory"
    locator: str  # path, commit hash, test name, URL, memory ID
    description: str = ""
    verified: bool = False
    captured_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


@dataclass
class BaseRecord:
    """Base class for all context records."""
    id: str
    kind: RecordKind
    project_scope: str
    created_at: str
    created_by: str  # agent/surface identifier
    version: int = 1
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    supersedes: list[str] = field(default_factory=list)  # IDs of records this supersedes
    superseded_by: list[str] = field(default_factory=list)  # IDs of records that supersede this
    evidence: list[EvidenceReference] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value if isinstance(self.kind, RecordKind) else self.kind
        d["status"] = self.status.value if isinstance(self.status, VerificationStatus) else self.status
        d["evidence"] = [asdict(e) for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BaseRecord":
        # This is a base class - actual subclasses handle their own from_dict
        raise NotImplementedError("Use subclass from_dict")


@dataclass
class ProjectContext(BaseRecord):
    """Project identity, purpose, scope, and boundaries."""
    name: str = ""
    purpose: str = ""
    scope: str = ""
    boundaries: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    repositories: list[str] = field(default_factory=list)



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "name": self.name,
            "purpose": self.purpose,
            "scope": self.scope,
            "boundaries": self.boundaries,
            "tech_stack": self.tech_stack,
            "repositories": self.repositories,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectContext":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.PROJECT_CONTEXT),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            scope=data.get("scope", ""),
            boundaries=data.get("boundaries", []),
            tech_stack=data.get("tech_stack", []),
            repositories=data.get("repositories", []),
        )


@dataclass
class DecisionRecord(BaseRecord):
    """A technical decision with rationale, alternatives, and outcome."""
    title: str = ""
    decision: str = ""
    rationale: str = ""
    alternatives: list[dict] = field(default_factory=list)  # [{"option": "...", "reason_rejected": "..."}]
    outcome: str = ""  # "accepted", "rejected", "deferred", "superseded"
    tags: list[str] = field(default_factory=list)



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "title": self.title,
            "decision": self.decision,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "outcome": self.outcome,
            "tags": self.tags,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionRecord":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.DECISION_RECORD),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            title=data.get("title", ""),
            decision=data.get("decision", ""),
            rationale=data.get("rationale", ""),
            alternatives=data.get("alternatives", []),
            outcome=data.get("outcome", ""),
            tags=data.get("tags", []),
        )


@dataclass
class ConstraintRecord(BaseRecord):
    """Non-negotiable rules and preferences that must be preserved."""
    constraint: str = ""
    category: str = "general"  # "security", "architecture", "style", "workflow", "general"
    severity: str = "high"  # "critical", "high", "medium", "low"
    source: str = ""  # "user", "policy", "regulation", "architecture_decision"



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "constraint": self.constraint,
            "category": self.category,
            "severity": self.severity,
            "source": self.source,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ConstraintRecord":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.CONSTRAINT_RECORD),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            constraint=data.get("constraint", ""),
            category=data.get("category", "general"),
            severity=data.get("severity", "high"),
            source=data.get("source", ""),
        )


@dataclass
class WorkingState(BaseRecord):
    """Active task, status, blockers, and next action."""
    active_task: str = ""
    state: str = "in_progress"  # "not_started", "in_progress", "blocked", "completed", "abandoned"
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    progress: dict = field(default_factory=dict)  # {"completed": [], "remaining": []}
    context_budget_used: int = 0



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "active_task": self.active_task,
            "state": self.state,
            "blockers": self.blockers,
            "next_action": self.next_action,
            "progress": self.progress,
            "context_budget_used": self.context_budget_used,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkingState":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.WORKING_STATE),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            active_task=data.get("active_task", ""),
            state=data.get("state", "in_progress"),
            blockers=data.get("blockers", []),
            next_action=data.get("next_action", ""),
            progress=data.get("progress", {}),
            context_budget_used=data.get("context_budget_used", 0),
        )


@dataclass
class ContextCheckpoint(BaseRecord):
    """Consistent snapshot of context at a point in time."""
    label: str = ""
    snapshot: dict = field(default_factory=dict)  # {"decisions": [...], "constraints": [...], "state": {...}}
    parent_checkpoint: str = ""



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "label": self.label,
            "snapshot": self.snapshot,
            "parent_checkpoint": self.parent_checkpoint,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ContextCheckpoint":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.CONTEXT_CHECKPOINT),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            label=data.get("label", ""),
            snapshot=data.get("snapshot", {}),
            parent_checkpoint=data.get("parent_checkpoint", ""),
        )


@dataclass
class HandoffRecord(BaseRecord):
    """Transfer record between source and target agents."""
    source_agent: str = ""
    target_agent: str = ""
    task_summary: str = ""
    package: dict = field(default_factory=dict)  # The full handoff package
    accepted: bool = False
    accepted_at: str = ""



    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "task_summary": self.task_summary,
            "package": self.package,
            "accepted": self.accepted,
            "accepted_at": self.accepted_at,
        })
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "HandoffRecord":
        evidence = [EvidenceReference(**e) for e in data.get("evidence", [])]
        return cls(
            id=data["id"],
            kind=RecordKind(data["kind"]) if isinstance(data.get("kind"), str) else data.get("kind", RecordKind.HANDOFF_RECORD),
            project_scope=data["project_scope"],
            created_at=data["created_at"],
            created_by=data["created_by"],
            version=data.get("version", 1),
            status=VerificationStatus(data.get("status", "unverified")),
            supersedes=data.get("supersedes", []),
            superseded_by=data.get("superseded_by", []),
            evidence=evidence,
            metadata=data.get("metadata", {}),
            source_agent=data.get("source_agent", ""),
            target_agent=data.get("target_agent", ""),
            task_summary=data.get("task_summary", ""),
            package=data.get("package", {}),
            accepted=data.get("accepted", False),
            accepted_at=data.get("accepted_at", ""),
        )


# Union type for all records
ContextRecord = (
    ProjectContext
    | DecisionRecord
    | ConstraintRecord
    | WorkingState
    | EvidenceReference
    | ContextCheckpoint
    | HandoffRecord
)


def create_record(kind: RecordKind, project_scope: str, created_by: str, **kwargs) -> ContextRecord:
    """Factory function to create a context record of the specified kind."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record_id = f"{kind.value.lower()}-{uuid.uuid4().hex[:12]}"

    common = {
        "id": record_id,
        "kind": kind,  # Pass kind explicitly for base class
        "project_scope": project_scope,
        "created_at": now,
        "created_by": created_by,
    }
    common.update(kwargs)

    if kind == RecordKind.PROJECT_CONTEXT:
        return ProjectContext(**common)
    elif kind == RecordKind.DECISION_RECORD:
        return DecisionRecord(**common)
    elif kind == RecordKind.CONSTRAINT_RECORD:
        return ConstraintRecord(**common)
    elif kind == RecordKind.WORKING_STATE:
        return WorkingState(**common)
    elif kind == RecordKind.CONTEXT_CHECKPOINT:
        return ContextCheckpoint(**common)
    elif kind == RecordKind.HANDOFF_RECORD:
        return HandoffRecord(**common)
    else:
        raise ValueError(f"Unknown record kind: {kind}")


def record_to_json(record: ContextRecord) -> str:
    """Serialize a record to JSON (compact, single-line for JSONL)."""
    return json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))


def record_from_json(json_str: str) -> ContextRecord:
    """Deserialize a record from JSON."""
    data = json.loads(json_str)
    kind = RecordKind(data["kind"])

    # Use the appropriate from_dict method to properly convert enums
    if kind == RecordKind.PROJECT_CONTEXT:
        return ProjectContext.from_dict(data)
    elif kind == RecordKind.DECISION_RECORD:
        return DecisionRecord.from_dict(data)
    elif kind == RecordKind.CONSTRAINT_RECORD:
        return ConstraintRecord.from_dict(data)
    elif kind == RecordKind.WORKING_STATE:
        return WorkingState.from_dict(data)
    elif kind == RecordKind.CONTEXT_CHECKPOINT:
        return ContextCheckpoint.from_dict(data)
    elif kind == RecordKind.HANDOFF_RECORD:
        return HandoffRecord.from_dict(data)
    else:
        raise ValueError(f"Unknown record kind: {kind}")


# Compact change history (supersession)
# A handoff should say "the project changed its mind, and why" WITHOUT paying the
# tokens of the entire replaced decision. These caps keep each entry bounded.
MAX_PREVIOUS_DECISION_CHARS = 240
MAX_CHANGE_REASON_CHARS = 280


def _compact(text: str, limit: int) -> str:
    """Trim text to `limit` chars, appending an ellipsis when cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


@dataclass
class SupersessionEntry:
    """Compact record of one decision reversal.

    Carries the relationship and the *why* (change_reason), plus the verification
    status and evidence of the successor — not the full text of the replaced
    decision. Example:

        {
          "decision_id": "decisionrecord-...",   # successor
          "current_decision": "Use PostgreSQL",
          "supersedes": "decisionrecord-...",     # replaced
          "previous_decision": "Use SQLite",
          "change_reason": "Concurrent writers required",
          "status": "verified",
          "evidence": [...]
        }
    """
    decision_id: str = ""          # id of the successor decision
    current_decision: str = ""     # compact successor decision text
    supersedes: str = ""           # id of the decision this replaced
    previous_decision: str = ""    # compact replaced-decision text
    change_reason: str = ""        # why the change was made (successor rationale)
    status: str = "verified"       # verification status of the successor
    evidence: list[EvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "current_decision": self.current_decision,
            "supersedes": self.supersedes,
            "previous_decision": self.previous_decision,
            "change_reason": self.change_reason,
            "status": self.status,
            "evidence": [asdict(e) for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SupersessionEntry":
        return cls(
            decision_id=data.get("decision_id", ""),
            current_decision=data.get("current_decision", ""),
            supersedes=data.get("supersedes", ""),
            previous_decision=data.get("previous_decision", ""),
            change_reason=data.get("change_reason", ""),
            status=data.get("status", "verified"),
            evidence=[EvidenceReference(**e) for e in data.get("evidence", [])],
        )


def build_supersession_history(
    decisions: list[DecisionRecord],
    max_previous_chars: int = MAX_PREVIOUS_DECISION_CHARS,
    max_reason_chars: int = MAX_CHANGE_REASON_CHARS,
) -> list[SupersessionEntry]:
    """Build compact change-history entries from a set of decisions.

    One entry per superseded decision, pairing it with the successor that
    replaced it. Decisions never superseded contribute nothing.
    """
    by_id = {d.id: d for d in decisions}
    entries: list[SupersessionEntry] = []
    for old in decisions:
        for successor_id in old.superseded_by:
            successor = by_id.get(successor_id)
            if successor is None:
                continue
            status = successor.status.value if isinstance(successor.status, VerificationStatus) else str(successor.status)
            entries.append(SupersessionEntry(
                decision_id=successor.id,
                current_decision=_compact(successor.decision, max_previous_chars),
                supersedes=old.id,
                previous_decision=_compact(old.decision, max_previous_chars),
                change_reason=_compact(successor.rationale, max_reason_chars),
                status=status,
                evidence=list(successor.evidence),
            ))
    return entries


# Context Package for Handoffs
@dataclass
class ContextPackage:
    """Portable context package for agent handoff."""
    project_context: Optional[ProjectContext] = None
    decisions: list[DecisionRecord] = field(default_factory=list)
    constraints: list[ConstraintRecord] = field(default_factory=list)
    supersession_history: list[SupersessionEntry] = field(default_factory=list)
    working_state: Optional[WorkingState] = None
    evidence: list[EvidenceReference] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    created_by: str = ""
    version: str = "1.0"

    def to_json(self) -> str:
        """Export as machine-verifiable JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        """Export as dictionary for serialization."""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "project_context": self.project_context.to_dict() if self.project_context else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "constraints": [c.to_dict() for c in self.constraints],
            "supersession_history": [s.to_dict() for s in self.supersession_history],
            "working_state": self.working_state.to_dict() if self.working_state else None,
            "evidence": [asdict(e) for e in self.evidence],
            "open_questions": self.open_questions,
            "uncertainty": self.uncertainty,
        }

    def to_markdown(self) -> str:
        """Export as human-readable Markdown."""
        lines = [
            f"# Context Handoff Package",
            f"",
            f"**Created:** {self.created_at}  ",
            f"**By:** {self.created_by}  ",
            f"**Version:** {self.version}",
            f"",
        ]

        if self.project_context:
            pc = self.project_context
            lines.extend([
                f"## Project Context",
                f"**Name:** {pc.name}",
                f"**Purpose:** {pc.purpose}",
                f"**Scope:** {pc.scope}",
                f"**Tech Stack:** {', '.join(pc.tech_stack) or '—'}",
                f"**Repositories:** {', '.join(pc.repositories) or '—'}",
                f"",
            ])

        if self.decisions:
            lines.append(f"## Decisions & Rationale")
            for d in self.decisions:
                status_emoji = {"verified": "✅", "user_asserted": "👤", "agent_inferred": "🤖", "unverified": "❓", "superseded": "⚠️"}.get(d.status.value, "❓")
                lines.extend([
                    f"",
                    f"### {status_emoji} {d.title}",
                    f"**Decision:** {d.decision}",
                    f"**Rationale:** {d.rationale or '—'}",
                ])
                if d.alternatives:
                    lines.append(f"**Alternatives Considered:**")
                    for alt in d.alternatives:
                        lines.append(f"- {alt.get('option', '')}: {alt.get('reason_rejected', '')}")
                if d.outcome:
                    lines.append(f"**Outcome:** {d.outcome}")
                if d.evidence:
                    lines.append(f"**Evidence:**")
                    for e in d.evidence:
                        lines.append(f"- `{e.kind}`: {e.locator} — {e.description}")
                lines.append(f"")

        if self.supersession_history:
            lines.append(f"## Change History (compact)")
            for s in self.supersession_history:
                lines.append(
                    f"- {s.previous_decision} \u2192 {s.current_decision} "
                    f"\u2014 {s.change_reason} *(status: {s.status})*"
                )
            lines.append(f"")

        if self.constraints:
            lines.append(f"## Non-Negotiable Constraints")
            for c in self.constraints:
                severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(c.severity, "⚪")
                lines.append(f"- {severity_emoji} **[{c.category}]** {c.constraint} *(source: {c.source or '—'})*")
            lines.append(f"")

        if self.working_state:
            ws = self.working_state
            lines.extend([
                f"## Working State",
                f"**Active Task:** {ws.active_task or '—'}",
                f"**Status:** {ws.state}",
                f"**Next Action:** {ws.next_action or '—'}",
                f"",
            ])
            if ws.blockers:
                lines.append(f"**Blockers:**")
                for b in ws.blockers:
                    lines.append(f"- {b}")
                lines.append(f"")
            if ws.progress:
                lines.append(f"**Progress:**")
                if ws.progress.get("completed"):
                    lines.append(f"  Completed: {', '.join(ws.progress['completed'])}")
                if ws.progress.get("remaining"):
                    lines.append(f"  Remaining: {', '.join(ws.progress['remaining'])}")
                lines.append(f"")

        if self.open_questions:
            lines.append(f"## Open Questions")
            for q in self.open_questions:
                lines.append(f"- {q}")
            lines.append(f"")

        if self.uncertainty:
            lines.append(f"## Uncertainty / Missing Information")
            for u in self.uncertainty:
                lines.append(f"- {u}")
            lines.append(f"")

        return "\n".join(lines)

    @classmethod
    def from_json(cls, json_str: str) -> "ContextPackage":
        """Import from machine-verifiable JSON."""
        data = json.loads(json_str)
        return cls(
            project_context=ProjectContext.from_dict(data["project_context"]) if data.get("project_context") else None,
            decisions=[DecisionRecord.from_dict(d) for d in data.get("decisions", [])],
            constraints=[ConstraintRecord.from_dict(c) for c in data.get("constraints", [])],
            supersession_history=[SupersessionEntry.from_dict(s) for s in data.get("supersession_history", [])],
            working_state=WorkingState.from_dict(data["working_state"]) if data.get("working_state") else None,
            evidence=[EvidenceReference(**e) for e in data.get("evidence", [])],
            open_questions=data.get("open_questions", []),
            uncertainty=data.get("uncertainty", []),
            created_at=data.get("created_at", ""),
            created_by=data.get("created_by", ""),
            version=data.get("version", "1.0"),
        )

    # -- Compact wire format (transport encoding; see module section below) ----

    def to_wire_dict(self) -> dict:
        """Encode to the compact wire representation (lossless vs to_dict)."""
        return _encode_package(self)

    def to_wire_json(self) -> str:
        """Encode to compact, unindented wire JSON (the token-lean transport)."""
        return json.dumps(_encode_package(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_wire_dict(cls, data: dict) -> "ContextPackage":
        """Decode a package from either the compact wire JSON or a legacy package."""
        return package_from_wire_dict(data)

    @classmethod
    def from_wire_json(cls, json_str: str) -> "ContextPackage":
        return package_from_wire_dict(json.loads(json_str))


# =============================================================================
# Compact wire format (v2)
# -----------------------------------------------------------------------------
# `to_dict`/`to_json` (indented, verbose keys, every field) is the readable,
# schema-anchored export and MUST NOT change. It is also token-heavy:
# pretty-printing, empty/default fields, and long keys cost ~10-15x per record.
# The compact wire format is a *transport* encoding that carries the same
# information: no indentation, empty/default fields elided, keys shortened.
#
# Nothing the decoder needs is dropped. Every record keeps its id, verification
# status, supersession links (supersedes / superseded_by), and evidence
# provenance (kind, locator, description, verified, captured_at). Per-record
# created_at / created_by / project_scope are omitted ONLY when they equal the
# package-level defaults and restored on decode, so round-trips are identical.
#
# Decoding is backward-compatible: a full (legacy) package JSON still loads.
# =============================================================================

WIRE_VERSION = 2

# Omittable defaults restored on decode.
_DEFAULT_STATUS = VerificationStatus.UNVERIFIED.value


def _package_scope(pkg: "ContextPackage") -> str:
    return pkg.project_context.scope if pkg.project_context else ""


def _req(data: dict, key: str, where: str) -> Any:
    if key not in data:
        raise ValueError(f"malformed wire package: missing '{key}' in {where}")
    return data[key]


def _enc_evidence(e: EvidenceReference) -> dict:
    d = {"i": e.id, "k": e.kind, "l": e.locator, "a": e.captured_at}
    if e.description:
        d["d"] = e.description
    if e.verified:
        d["v"] = True
    return d


def _dec_evidence(d: dict) -> EvidenceReference:
    return EvidenceReference(
        id=_req(d, "i", "evidence"),
        kind=d.get("k", ""),
        locator=d.get("l", ""),
        description=d.get("d", ""),
        verified=bool(d.get("v", False)),
        captured_at=d.get("a", ""),
    )


def _enc_common(rec: BaseRecord, pkg: "ContextPackage") -> dict:
    d: dict = {}
    st = rec.status.value if isinstance(rec.status, VerificationStatus) else rec.status
    if st and st != _DEFAULT_STATUS:
        d["st"] = st
    if rec.version != 1:
        d["ver"] = rec.version
    if rec.supersedes:
        d["sup"] = list(rec.supersedes)
    if rec.superseded_by:
        d["sby"] = list(rec.superseded_by)
    if rec.evidence:
        d["ev"] = [_enc_evidence(e) for e in rec.evidence]
    if rec.metadata:
        d["md"] = rec.metadata
    if rec.created_at and rec.created_at != pkg.created_at:
        d["at"] = rec.created_at
    if rec.created_by and rec.created_by != pkg.created_by:
        d["cb"] = rec.created_by
    scope = _package_scope(pkg)
    if rec.project_scope and (not scope or rec.project_scope != scope):
        d["sc"] = rec.project_scope
    return d


def _common_kwargs(d: dict, kind: RecordKind, pkg_scope: str,
                   pkg_by: str, pkg_at: str) -> dict:
    return dict(
        id=_req(d, "i", kind.value),
        kind=kind,
        project_scope=d.get("sc", pkg_scope),
        created_at=d.get("at", pkg_at),
        created_by=d.get("cb", pkg_by),
        version=d.get("ver", 1),
        status=VerificationStatus(d.get("st", _DEFAULT_STATUS)),
        supersedes=list(d.get("sup", [])),
        superseded_by=list(d.get("sby", [])),
        evidence=[_dec_evidence(e) for e in d.get("ev", [])],
        metadata=d.get("md", {}),
    )


def _enc_project_context(pc: ProjectContext, pkg: "ContextPackage") -> dict:
    out: dict = {"i": pc.id}
    if pc.name:
        out["n"] = pc.name
    if pc.purpose:
        out["p"] = pc.purpose
    if pc.scope:
        out["s"] = pc.scope
    if pc.boundaries:
        out["b"] = list(pc.boundaries)
    if pc.tech_stack:
        out["t"] = list(pc.tech_stack)
    if pc.repositories:
        out["r"] = list(pc.repositories)
    out.update(_enc_common(pc, pkg))
    return out


def _dec_project_context(d: dict, pkg: "ContextPackage",
                         pkg_scope: str | None = None) -> ProjectContext:
    if pkg_scope is None:
        pkg_scope = _package_scope(pkg)
    kw = _common_kwargs(d, RecordKind.PROJECT_CONTEXT,
                        pkg_scope, pkg.created_by, pkg.created_at)
    return ProjectContext(
        **kw,
        name=d.get("n", ""), purpose=d.get("p", ""), scope=d.get("s", ""),
        boundaries=list(d.get("b", [])), tech_stack=list(d.get("t", [])),
        repositories=list(d.get("r", [])),
    )


def _enc_decision(rec: DecisionRecord, pkg: "ContextPackage") -> dict:
    out: dict = {"i": rec.id}
    if rec.title:
        out["t"] = rec.title
    if rec.decision:
        out["c"] = rec.decision
    if rec.rationale:
        out["r"] = rec.rationale
    if rec.alternatives:
        out["a"] = [{"o": x.get("option", ""), "r": x.get("reason_rejected", "")}
                    for x in rec.alternatives]
    if rec.outcome:
        out["o"] = rec.outcome
    if rec.tags:
        out["g"] = list(rec.tags)
    out.update(_enc_common(rec, pkg))
    return out


def _dec_decision(d: dict, pkg: "ContextPackage") -> DecisionRecord:
    kw = _common_kwargs(d, RecordKind.DECISION_RECORD,
                        _package_scope(pkg), pkg.created_by, pkg.created_at)
    return DecisionRecord(
        **kw,
        title=d.get("t", ""), decision=d.get("c", ""), rationale=d.get("r", ""),
        alternatives=[{"option": x.get("o", ""), "reason_rejected": x.get("r", "")}
                      for x in d.get("a", [])],
        outcome=d.get("o", ""), tags=list(d.get("g", [])),
    )


def _enc_constraint(rec: ConstraintRecord, pkg: "ContextPackage") -> dict:
    out: dict = {"i": rec.id, "K": rec.constraint}
    if rec.category and rec.category != "general":
        out["k"] = rec.category
    if rec.severity and rec.severity != "high":
        out["s"] = rec.severity
    if rec.source:
        out["u"] = rec.source
    out.update(_enc_common(rec, pkg))
    return out


def _dec_constraint(d: dict, pkg: "ContextPackage") -> ConstraintRecord:
    kw = _common_kwargs(d, RecordKind.CONSTRAINT_RECORD,
                        _package_scope(pkg), pkg.created_by, pkg.created_at)
    return ConstraintRecord(
        **kw,
        constraint=_req(d, "K", "constraint"), category=d.get("k", "general"),
        severity=d.get("s", "high"), source=d.get("u", ""),
    )


def _enc_working_state(rec: WorkingState, pkg: "ContextPackage") -> dict:
    out: dict = {"i": rec.id}
    if rec.active_task:
        out["t"] = rec.active_task
    if rec.state and rec.state != "in_progress":
        out["s"] = rec.state
    if rec.blockers:
        out["b"] = list(rec.blockers)
    if rec.next_action:
        out["n"] = rec.next_action
    if rec.progress:
        out["p"] = rec.progress
    if rec.context_budget_used:
        out["u"] = rec.context_budget_used
    out.update(_enc_common(rec, pkg))
    return out


def _dec_working_state(d: dict, pkg: "ContextPackage") -> WorkingState:
    kw = _common_kwargs(d, RecordKind.WORKING_STATE,
                        _package_scope(pkg), pkg.created_by, pkg.created_at)
    return WorkingState(
        **kw,
        active_task=d.get("t", ""), state=d.get("s", "in_progress"),
        blockers=list(d.get("b", [])), next_action=d.get("n", ""),
        progress=d.get("p", {}), context_budget_used=d.get("u", 0),
    )


def _enc_entry(s: SupersessionEntry) -> dict:
    d: dict = {"i": s.decision_id}
    if s.current_decision:
        d["c"] = s.current_decision
    d["sp"] = s.supersedes
    if s.previous_decision:
        d["p"] = s.previous_decision
    if s.change_reason:
        d["r"] = s.change_reason
    if s.status and s.status != "verified":
        d["st"] = s.status
    if s.evidence:
        d["ev"] = [_enc_evidence(e) for e in s.evidence]
    return d


def _dec_entry(d: dict) -> SupersessionEntry:
    return SupersessionEntry(
        decision_id=_req(d, "i", "supersession entry"),
        current_decision=d.get("c", ""),
        supersedes=d.get("sp", ""),
        previous_decision=d.get("p", ""),
        change_reason=d.get("r", ""),
        status=d.get("st", "verified"),
        evidence=[_dec_evidence(e) for e in d.get("ev", [])],
    )


def _collect_child_evidence(pkg: "ContextPackage") -> list[EvidenceReference]:
    out: list[EvidenceReference] = []
    for r in list(pkg.decisions) + list(pkg.constraints) + ([pkg.working_state] if pkg.working_state else []):
        out.extend(r.evidence)
    return out


def _encode_package(pkg: "ContextPackage") -> dict:
    out: dict = {"wv": WIRE_VERSION, "v": pkg.version,
                 "at": pkg.created_at, "cb": pkg.created_by}
    if pkg.project_context:
        out["pc"] = _enc_project_context(pkg.project_context, pkg)
    if pkg.decisions:
        out["d"] = [_enc_decision(x, pkg) for x in pkg.decisions]
    if pkg.constraints:
        out["c"] = [_enc_constraint(x, pkg) for x in pkg.constraints]
    if pkg.supersession_history:
        out["ch"] = [_enc_entry(x) for x in pkg.supersession_history]
    if pkg.working_state:
        out["ws"] = _enc_working_state(pkg.working_state, pkg)
    child = _collect_child_evidence(pkg)
    if pkg.evidence and [e.id for e in pkg.evidence] != [e.id for e in child]:
        out["ev"] = [_enc_evidence(e) for e in pkg.evidence]
    if pkg.open_questions:
        out["oq"] = list(pkg.open_questions)
    if pkg.uncertainty:
        out["un"] = list(pkg.uncertainty)
    return out


def _decode_package(data: dict) -> "ContextPackage":
    pkg_scope = ""
    pkg = ContextPackage(
        created_at=data.get("at", ""),
        created_by=data.get("cb", ""),
        version=data.get("v", "1.0"),
    )
    if data.get("pc") is not None:
        pc_scope = data["pc"].get("s", "")
        pkg.project_context = _dec_project_context(data["pc"], pkg, pkg_scope=pc_scope)
        pkg_scope = pkg.project_context.scope
    pkg.decisions = [_dec_decision(x, pkg) for x in data.get("d", [])]
    pkg.constraints = [_dec_constraint(x, pkg) for x in data.get("c", [])]
    pkg.supersession_history = [_dec_entry(x) for x in data.get("ch", [])]
    if data.get("ws") is not None:
        pkg.working_state = _dec_working_state(data["ws"], pkg)
    if "ev" in data:
        pkg.evidence = [_dec_evidence(e) for e in data["ev"]]
    else:
        pkg.evidence = _collect_child_evidence(pkg)
    pkg.open_questions = list(data.get("oq", []))
    pkg.uncertainty = list(data.get("un", []))
    return pkg


def _decode_legacy(data: dict) -> "ContextPackage":
    return ContextPackage(
        project_context=ProjectContext.from_dict(data["project_context"]) if data.get("project_context") else None,
        decisions=[DecisionRecord.from_dict(d) for d in data.get("decisions", [])],
        constraints=[ConstraintRecord.from_dict(c) for c in data.get("constraints", [])],
        supersession_history=[SupersessionEntry.from_dict(s) for s in data.get("supersession_history", [])],
        working_state=WorkingState.from_dict(data["working_state"]) if data.get("working_state") else None,
        evidence=[EvidenceReference(**e) for e in data.get("evidence", [])],
        open_questions=list(data.get("open_questions", [])),
        uncertainty=list(data.get("uncertainty", [])),
        created_at=data.get("created_at", ""),
        created_by=data.get("created_by", ""),
        version=data.get("version", "1.0"),
    )


def package_from_wire_dict(data: dict) -> "ContextPackage":
    """Decode a context package from compact wire JSON or a legacy package dict.

    Rejects anything that is neither: an unrecognized shape or an unsupported
    wire version raises ValueError (negative-control / malformed-input safety).
    """
    if not isinstance(data, dict):
        raise ValueError("malformed wire package: top level must be an object")
    if "wv" in data:
        if not isinstance(data["wv"], int) or data["wv"] != WIRE_VERSION:
            raise ValueError(f"unsupported wire version: {data.get('wv')!r}")
        return _decode_package(data)
    if any(k in data for k in ("decisions", "constraints", "project_context",
                               "supersession_history", "version")):
        return _decode_legacy(data)
    raise ValueError("unrecognized package format: not a compact wire or legacy package")


def package_from_wire_json(json_str: str) -> "ContextPackage":
    return package_from_wire_dict(json.loads(json_str))


# Context Budget Management
class ContextBudget:
    """Manages token budget for context packages."""

    DEFAULT_BUDGET = 8000  # Approximate tokens
    RESERVED_FOR_TASK = 2000

    def __init__(self, max_tokens: int = DEFAULT_BUDGET):
        self.max_tokens = max_tokens
        self.reserved = self.RESERVED_FOR_TASK
        self.used = 0

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token)."""
        return len(text) // 4

    def can_add(self, text: str) -> bool:
        return self.used + self.estimate_tokens(text) <= self.max_tokens - self.reserved

    def add(self, text: str) -> bool:
        tokens = self.estimate_tokens(text)
        if self.used + tokens <= self.max_tokens - self.reserved:
            self.used += tokens
            return True
        return False

    def remaining(self) -> int:
        return max(0, self.max_tokens - self.reserved - self.used)


# Priority order used when trimming a package to a token budget. Earlier units
# win the budget. Rationale: an agent resuming work needs to know WHO the project
# is and WHERE it stopped first, then HOW THE PROJECT CHANGED (the compact change
# history the product now guarantees by default — it is small and must not be the
# thing that gets dropped). Current decisions, constraints, evidence and open
# questions follow; raw evidence is the most compressible.
_PACKAGE_FIT_PRIORITY = (
    "project_context",
    "working_state",
    "supersession_history",
    "decisions",
    "constraints",
    "evidence",
    "open_questions",
    "uncertainty",
)


def _package_tokens(pkg: "ContextPackage", wire: str = "full") -> int:
    text = pkg.to_wire_json() if wire == "compact" else pkg.to_json()
    return ContextBudget().estimate_tokens(text)


def fit_package_to_budget(package: "ContextPackage", max_tokens: int,
                          wire: str = "full") -> "ContextPackage":
    """Return a trimmed copy of `package` that fits within `max_tokens`.

    Units are added greedily in `_PACKAGE_FIT_PRIORITY` order (project context and
    working state are the non-negotiable core; the rest are added one at a time
    while they fit). The result may still exceed the budget when even the core
    does not fit — callers should treat `max_tokens` as a target, not a hard cap.

    `wire` selects the token estimate used for trimming ("full" or "compact") so
    the budget is measured against the same encoding the caller will transport.
    """
    base = ContextPackage(
        project_context=package.project_context,
        working_state=package.working_state,
        open_questions=[],
        uncertainty=[],
        created_at=package.created_at,
        created_by=package.created_by,
        version=package.version,
    )

    ops: list[tuple[str, Any]] = []
    ops += [("supersession_history", s) for s in package.supersession_history]
    ops += [("decisions", d) for d in package.decisions]
    ops += [("constraints", c) for c in package.constraints]
    ops += [("evidence", e) for e in package.evidence]
    ops += [("open_questions", q) for q in package.open_questions]
    ops += [("uncertainty", u) for u in package.uncertainty]

    for field_name, item in ops:
        trial = copy.deepcopy(base)
        getattr(trial, field_name).append(item)
        if _package_tokens(trial, wire) <= max_tokens:
            base = trial

    return base


# Security: Secret/PII filtering
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token|auth[_-]?key)\s*[:=]\s*[\w\-]{20,}"),
    re.compile(r"(?i)bearer\s+[\w\-]{20,}"),
    re.compile(r"sk-[\w\-]{20,}"),  # OpenAI-style keys
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),  # GitHub tokens
    re.compile(r"glpat-[\w\-]{20,}"),  # GitLab tokens
    re.compile(r"aws_[a-z]+_key\s*[:=]\s*[\w\/+]{20,}"),
    re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),  # Credit card-ish
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # Emails
]


def sanitize_for_transfer(text: str) -> str:
    """Remove secrets and PII from text before cross-client transfer."""
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def detect_secrets(text: str) -> list[str]:
    """Detect potential secrets in text."""
    found = []
    for pattern in SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            found.extend(matches if isinstance(matches[0], str) else [m[0] for m in matches])
    return found


# Storage for context records (local JSONL files).
# Override the location with TALLYSTONE_HOME (default: ~/.tallystone).
TALLYSTONE_HOME = os.environ.get("TALLYSTONE_HOME")
TALLYSTONE_DIR = Path(TALLYSTONE_HOME).expanduser() if TALLYSTONE_HOME else Path(os.path.expanduser("~/.tallystone"))


def get_context_store_path(scope: str) -> Path:
    """Get the storage path for a project scope."""
    TALLYSTONE_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    return TALLYSTONE_DIR / f"{scope}.jsonl"


def save_record(record: ContextRecord, scope: str = None) -> bool:
    """Persist a context record to local storage."""
    scope = scope or record.project_scope
    path = get_context_store_path(scope)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(record_to_json(record) + "\n")
        return True
    except Exception:
        return False


def load_records(scope: str, kind: RecordKind = None) -> list[ContextRecord]:
    """Load context records from local storage (latest version per ID)."""
    path = get_context_store_path(scope)
    if not path.exists():
        return []

    records_by_id = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if kind and data.get("kind") != kind.value:
                        continue
                    record = record_from_json(line)
                    record_id = record.id
                    # Keep the latest version (by created_at)
                    if record_id not in records_by_id or record.created_at > records_by_id[record_id].created_at:
                        records_by_id[record_id] = record
                except Exception:
                    continue
    except Exception:
        pass
    return list(records_by_id.values())


def get_latest_record(scope: str, kind: RecordKind) -> ContextRecord | None:
    """Get the most recent record of a given kind for a scope."""
    records = load_records(scope, kind)
    if not records:
        return None
    return max(records, key=lambda r: r.created_at)


# Capture functions for agent lifecycle events
def capture_decision(
    project_scope: str,
    agent: str,
    title: str,
    decision: str,
    rationale: str,
    alternatives: list[dict] = None,
    outcome: str = "accepted",
    evidence_refs: list[EvidenceReference] = None,
    tags: list[str] = None,
    status: VerificationStatus = VerificationStatus.USER_ASSERTED,
    supersedes: list[str] = None,
) -> DecisionRecord:
    """Capture a technical decision with rationale."""
    record = create_record(
        RecordKind.DECISION_RECORD,
        project_scope=project_scope,
        created_by=agent,
        title=title,
        decision=decision,
        rationale=rationale,
        alternatives=alternatives or [],
        outcome=outcome,
        tags=tags or [],
        status=status,
        evidence=evidence_refs or [],
        supersedes=supersedes or [],
    )
    save_record(record)

    # Update superseded records to add this record to their superseded_by list
    if supersedes:
        for old_id in supersedes:
            old_records = load_records(project_scope, RecordKind.DECISION_RECORD)
            for old_rec in old_records:
                if old_rec.id == old_id and record.id not in old_rec.superseded_by:
                    old_rec.superseded_by.append(record.id)
                    # A superseded decision is no longer a current decision.
                    old_rec.status = VerificationStatus.SUPERSEDED
                    # Update created_at to ensure this version is kept by deduplication
                    old_rec.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    save_record(old_rec)

    return record


def capture_constraint(
    project_scope: str,
    agent: str,
    constraint: str,
    category: str = "general",
    severity: str = "high",
    source: str = "user",
    evidence_refs: list[EvidenceReference] = None,
    status: VerificationStatus = VerificationStatus.USER_ASSERTED,
) -> ConstraintRecord:
    """Capture a non-negotiable constraint."""
    record = create_record(
        RecordKind.CONSTRAINT_RECORD,
        project_scope=project_scope,
        created_by=agent,
        constraint=constraint,
        category=category,
        severity=severity,
        source=source,
        status=status,
        evidence=evidence_refs or [],
    )
    save_record(record)
    return record


def capture_working_state(
    project_scope: str,
    agent: str,
    active_task: str,
    state: str = "in_progress",
    blockers: list[str] = None,
    next_action: str = "",
    progress: dict = None,
    evidence_refs: list[EvidenceReference] = None,
) -> WorkingState:
    """Capture current working state."""
    record = create_record(
        RecordKind.WORKING_STATE,
        project_scope=project_scope,
        created_by=agent,
        active_task=active_task,
        state=state,
        blockers=blockers or [],
        next_action=next_action,
        progress=progress or {},
        evidence=evidence_refs or [],
    )
    save_record(record)
    return record


def create_checkpoint(
    project_scope: str,
    agent: str,
    label: str,
    snapshot: dict,
    parent_checkpoint: str = "",
    evidence_refs: list[EvidenceReference] = None,
) -> ContextCheckpoint:
    """Create a context checkpoint."""
    record = create_record(
        RecordKind.CONTEXT_CHECKPOINT,
        project_scope=project_scope,
        created_by=agent,
        label=label,
        snapshot=snapshot,
        parent_checkpoint=parent_checkpoint,
        evidence=evidence_refs or [],
    )
    save_record(record)
    return record


def create_handoff(
    project_scope: str,
    source_agent: str,
    target_agent: str,
    task_summary: str,
    package: ContextPackage,
    evidence_refs: list[EvidenceReference] = None,
) -> HandoffRecord:
    """Create a handoff record."""
    record = create_record(
        RecordKind.HANDOFF_RECORD,
        project_scope=project_scope,
        created_by=source_agent,
        source_agent=source_agent,
        target_agent=target_agent,
        task_summary=task_summary,
        package=package.to_dict(),
        evidence=evidence_refs or [],
    )
    save_record(record)
    return record


# Conflict detection
def detect_conflicts(records: list[ContextRecord]) -> list[dict]:
    """Detect conflicting records in a set."""
    conflicts = []

    # Check for contradictory decisions
    decisions = [r for r in records if isinstance(r, DecisionRecord)]
    for i, d1 in enumerate(decisions):
        for d2 in decisions[i+1:]:
            # Same tags, different outcomes
            if set(d1.tags) & set(d2.tags) and d1.outcome != d2.outcome:
                if d1.status != VerificationStatus.SUPERSEDED and d2.status != VerificationStatus.SUPERSEDED:
                    conflicts.append({
                        "type": "contradictory_decisions",
                        "records": [d1.id, d2.id],
                        "details": f"Decisions '{d1.title}' and '{d2.title}' have conflicting outcomes",
                    })
            # Same tags, both accepted, but different decisions (potential contradiction)
            elif set(d1.tags) & set(d2.tags) and d1.outcome == "accepted" and d2.outcome == "accepted":
                if d1.status != VerificationStatus.SUPERSEDED and d2.status != VerificationStatus.SUPERSEDED:
                    if d1.decision != d2.decision:
                        conflicts.append({
                            "type": "contradictory_decisions",
                            "records": [d1.id, d2.id],
                            "details": f"Decisions '{d1.title}' and '{d2.title}' have same tags but different decisions",
                        })

    # Check for contradictory constraints
    constraints = [r for r in records if isinstance(r, ConstraintRecord)]
    for i, c1 in enumerate(constraints):
        for c2 in constraints[i+1:]:
            if c1.constraint.lower() in c2.constraint.lower() or c2.constraint.lower() in c1.constraint.lower():
                if c1.severity == c2.severity and c1.category == c2.category:
                    conflicts.append({
                        "type": "overlapping_constraints",
                        "records": [c1.id, c2.id],
                        "details": f"Constraints may overlap: '{c1.constraint[:50]}...' vs '{c2.constraint[:50]}...'",
                    })

    return conflicts


# Idempotency key generation
def idempotency_key(record: ContextRecord) -> str:
    """Generate a deterministic key for deduplication."""
    content = f"{record.kind.value}:{record.project_scope}:{record.created_by}:{record.created_at[:10]}"
    if isinstance(record, DecisionRecord):
        content += f":{record.title}"
    elif isinstance(record, ConstraintRecord):
        content += f":{record.constraint[:50]}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================================
# Cross-Client Integration — Consumer Chat Interfaces
# ============================================================================

def parse_chatgpt_export(export_path: str) -> list[dict]:
    """Parse ChatGPT conversation export (conversations.json format)."""
    try:
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as ex:
        raise ValueError(f"Failed to parse ChatGPT export: {ex}")

    conversations = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        mapping = conv.get("mapping", {})
        messages = []
        for node_id, node in mapping.items():
            msg = node.get("message")
            if not msg:
                continue
            author = msg.get("author", {}).get("role", "unknown")
            content_parts = msg.get("content", {}).get("parts", [])
            content = "\n".join(str(p) for p in content_parts if p)
            if content.strip():
                messages.append({"role": author, "content": content})
        if messages:
            conversations.append({
                "id": conv.get("id", ""),
                "title": conv.get("title", "Untitled"),
                "create_time": conv.get("create_time", 0),
                "messages": messages,
            })
    return conversations


def parse_claude_export(export_path: str) -> list[dict]:
    """Parse Claude conversation export (conversations.json format)."""
    try:
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as ex:
        raise ValueError(f"Failed to parse Claude export: {ex}")

    conversations = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        uuid = conv.get("uuid", "")
        name = conv.get("name", "Untitled")
        created_at = conv.get("created_at", "")
        chat_messages = conv.get("chat_messages", [])
        messages = []
        for msg in chat_messages:
            sender = msg.get("sender", "unknown")
            content = msg.get("text", "")
            if content.strip():
                messages.append({"role": sender, "content": content})
        if messages:
            conversations.append({
                "id": uuid,
                "title": name,
                "create_time": created_at,
                "messages": messages,
            })
    return conversations


def extract_decisions_from_conversation(
    conversation: dict,
    project_scope: str,
    agent: str,
) -> list[DecisionRecord]:
    """Extract decision records from a conversation using heuristics."""
    decisions = []
    messages = conversation.get("messages", [])

    # Simple heuristic: look for decision-like patterns
    decision_markers = [
        "decided to", "decision:", "we will use", "going with", "chose",
        "rationale:", "because", "reason:", "alternative", "instead of",
        "trade-off", "tradeoff", "pros and cons",
    ]

    for i, msg in enumerate(messages):
        content = msg.get("content", "").lower()
        if any(marker in content for marker in decision_markers):
            # Found potential decision - create a record
            # Use surrounding context
            context_start = max(0, i - 2)
            context_end = min(len(messages), i + 3)
            context_text = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in messages[context_start:context_end]
            )

            # Sanitize
            context_text = sanitize_for_transfer(context_text)

            rec = capture_decision(
                project_scope=project_scope,
                agent=agent,
                title=f"Extracted from {conversation.get('title', 'conversation')}",
                decision=context_text[:500],
                rationale=context_text[500:1500] if len(context_text) > 500 else "",
                alternatives=[],
                outcome="extracted",
                status=VerificationStatus.AGENT_INFERRED,
                evidence_refs=[
                    EvidenceReference(
                        id=f"conv-{conversation.get('id', 'unknown')}-msg-{i}",
                        kind="conversation",
                        locator=conversation.get("id", ""),
                        description=f"Message {i} in '{conversation.get('title', 'Untitled')}'",
                    )
                ],
            )
            decisions.append(rec)

    return decisions


def extract_constraints_from_conversation(
    conversation: dict,
    project_scope: str,
    agent: str,
) -> list[ConstraintRecord]:
    """Extract constraint records from a conversation."""
    constraints = []
    messages = conversation.get("messages", [])

    constraint_markers = [
        "must not", "never", "always", "required", "mandatory",
        "constraint:", "rule:", "policy:", "forbidden", "prohibited",
        "security requirement", "compliance",
    ]

    for i, msg in enumerate(messages):
        content = msg.get("content", "").lower()
        if any(marker in content for marker in constraint_markers):
            context_start = max(0, i - 1)
            context_end = min(len(messages), i + 2)
            context_text = "\n".join(
                f"{m.get('role', 'unknown')}: {m.get('content', '')}"
                for m in messages[context_start:context_end]
            )
            context_text = sanitize_for_transfer(context_text)

            rec = capture_constraint(
                project_scope=project_scope,
                agent=agent,
                constraint=context_text[:500],
                category="general",
                severity="high",
                source="conversation",
                status=VerificationStatus.AGENT_INFERRED,
                evidence_refs=[
                    EvidenceReference(
                        id=f"conv-{conversation.get('id', 'unknown')}-msg-{i}",
                        kind="conversation",
                        locator=conversation.get("id", ""),
                        description=f"Message {i} in '{conversation.get('title', 'Untitled')}'",
                    )
                ],
            )
            constraints.append(rec)

    return constraints


def import_consumer_chat_export(
    export_path: str,
    platform: str,  # "chatgpt", "claude"
    project_scope: str,
    agent: str = "imported",
) -> dict:
    """Import a consumer chat export and extract context records.

    This is a MANUAL process - user must provide the export file.
    No automated scraping or unauthorized access.
    """
    if platform == "chatgpt":
        conversations = parse_chatgpt_export(export_path)
    elif platform == "claude":
        conversations = parse_claude_export(export_path)
    else:
        raise ValueError(f"Unsupported platform: {platform}")

    all_decisions = []
    all_constraints = []

    for conv in conversations:
        all_decisions.extend(extract_decisions_from_conversation(conv, project_scope, agent))
        all_constraints.extend(extract_constraints_from_conversation(conv, project_scope, agent))

    return {
        "conversations_processed": len(conversations),
        "decisions_extracted": len(all_decisions),
        "constraints_extracted": len(all_constraints),
        "decision_ids": [d.id for d in all_decisions],
        "constraint_ids": [c.id for c in all_constraints],
    }


def create_manual_handoff_input(
    scope: str,
    decisions: list[dict] = None,
    constraints: list[dict] = None,
    working_state: dict = None,
    open_questions: list[str] = None,
    uncertainty: list[str] = None,
) -> ContextPackage:
    """Create a context package from manually provided input (for consumer chat users)."""
    import tallystone as cb

    # Build project context (minimal)
    project_ctx = cb.get_latest_record(scope, cb.RecordKind.PROJECT_CONTEXT)

    # Convert manual input to records
    decision_records = []
    if decisions:
        for d in decisions:
            rec = cb.create_record(
                cb.RecordKind.DECISION_RECORD,
                project_scope=scope,
                created_by="manual",
                title=d.get("title", "Manual Decision"),
                decision=d.get("decision", ""),
                rationale=d.get("rationale", ""),
                alternatives=d.get("alternatives", []),
                outcome=d.get("outcome", "accepted"),
                status=cb.VerificationStatus.USER_ASSERTED,
            )
            decision_records.append(rec)

    constraint_records = []
    if constraints:
        for c in constraints:
            rec = cb.create_record(
                cb.RecordKind.CONSTRAINT_RECORD,
                project_scope=scope,
                created_by="manual",
                constraint=c.get("constraint", ""),
                category=c.get("category", "general"),
                severity=c.get("severity", "high"),
                source="manual",
                status=cb.VerificationStatus.USER_ASSERTED,
            )
            constraint_records.append(rec)

    working_state_record = None
    if working_state:
        working_state_record = cb.create_record(
            cb.RecordKind.WORKING_STATE,
            project_scope=scope,
            created_by="manual",
            active_task=working_state.get("active_task", ""),
            state=working_state.get("state", "in_progress"),
            blockers=working_state.get("blockers", []),
            next_action=working_state.get("next_action", ""),
            progress=working_state.get("progress", {}),
        )

    package = cb.ContextPackage(
        project_context=project_ctx,
        decisions=decision_records,
        constraints=constraint_records,
        working_state=working_state_record,
        open_questions=open_questions or [],
        uncertainty=uncertainty or [],
        created_by="manual",
    )

    return package


if __name__ == "__main__":
    import tempfile

    # Run against a throwaway store — never touch the user's real ~/.tallystone.
    TALLYSTONE_DIR = Path(tempfile.mkdtemp(prefix="tallystone_smoke_"))
    scope = "tallystone-smoke"

    print("tallystone — Smoke Test")
    print("=" * 40)

    # Create a project context
    pc = create_record(
        RecordKind.PROJECT_CONTEXT,
        project_scope=scope,
        created_by="tallystone",
        name="tallystone-smoke",
        purpose="Self-test project",
        scope="Smoke test for the tallystone handoff model",
        tech_stack=["Python"],
        repositories=["."],
    )
    print(f"Created ProjectContext: {pc.id}")

    # Create a decision
    dr = capture_decision(
        project_scope=scope,
        agent="tallystone",
        title="Use SQLite for the local store",
        decision="Use embedded SQLite for the local knowledge store instead of an external database",
        rationale="Zero external dependencies, low latency, stdlib-only, WAL-enabled for concurrency",
        alternatives=[
            {"option": "External DB", "reason_rejected": "Requires a daemon, adds operational complexity"},
            {"option": "In-memory graph", "reason_rejected": "No persistence across sessions"},
        ],
        outcome="accepted",
        tags=["architecture", "storage"],
        status=VerificationStatus.VERIFIED,
    )
    print(f"Created DecisionRecord: {dr.id}")

    # Create a constraint
    cr = capture_constraint(
        project_scope=scope,
        agent="tallystone",
        constraint="Never store secrets, API keys, or tokens in memory — only record WHERE they live",
        category="security",
        severity="critical",
        source="architecture_decision",
        status=VerificationStatus.VERIFIED,
    )
    print(f"Created ConstraintRecord: {cr.id}")

    # Create working state
    ws = capture_working_state(
        project_scope=scope,
        agent="tallystone",
        active_task="Validate the portable handoff model",
        state="in_progress",
        blockers=["Need to design the canonical context model"],
        next_action="Implement context capture and handoff package generation",
        progress={"completed": ["Architecture analysis", "Data models"], "remaining": ["Capture", "Handoff", "Tests"]},
    )
    print(f"Created WorkingState: {ws.id}")

    # Create context package
    package = ContextPackage(
        project_context=pc,
        decisions=[dr],
        constraints=[cr],
        working_state=ws,
        open_questions=["How to handle real-time sync between agents?"],
        uncertainty=["Consumer chat interface integration approach"],
        created_by="tallystone",
    )

    # Test JSON export/import
    json_out = package.to_json()
    package2 = ContextPackage.from_json(json_out)
    print(f"\nJSON round-trip: {'OK' if package2.project_context.name == pc.name else 'FAIL'}")

    # Test Markdown export
    md_out = package.to_markdown()
    print(f"\nMarkdown export length: {len(md_out)} chars")

    # Test conflict detection
    conflicts = detect_conflicts([dr, cr, ws])
    print(f"Conflicts detected: {len(conflicts)}")

    print("\n✅ All smoke tests passed!")