#!/usr/bin/env python3
"""
tallystone Benchmark — prove (or disprove) that structured context handoff
beats a naive chat summary for cross-agent continuity.

This is a REPRODUCIBLE benchmark. Given a fixed seed it produces the identical
scenario, the identical transports, and the identical scores on every machine,
with no network access required.

What it measures
----------------
Transports carry the same project context from a "source" agent to a "target":

  * TALLYSTONE — the structured handoff package produced by the tallystone core.
    Three modes mirroring `--history`:
        - compact (DEFAULT): current decisions + compact change history
        - current: current decisions only, no change history
        - audit  : every full decision record, superseded ones included
  * CHAT_SUMMARY   — a Markdown summary of the kind a chat model writes at the
    end of a session. Three strengths:
        - terse   : decisions + constraints + next steps, no rationale
        - verbose : the above PLUS rationale for every decision
        - history : verbose PLUS a "what changed" section (strongest baseline)

For each transport we score how much *critical context* survives:

  decision_recall          fraction of CURRENT decisions whose statement survives
  rationale_preservation   fraction of CURRENT decisions whose rationale survives
  constraint_recall        fraction of constraints that survive
  evidence_provenance      fraction of evidence locators (file/commit/test) that survive
  change_history           fraction of SUPERSEDED decisions whose replacement is visible
  conflict_visibility      fraction of planted contradictions that stay detectable
  pending_task_recall      fraction of pending tasks that survive

  critical_fact_preservation = mean of the above (each axis weighted equally)
  tokens                     = estimated transport size (len // 4)

Equal-budget sweep
------------------
The default run is NOT a single comparison: every method is greedily filled to
the SAME token budget (1000/2000/4000/8000/16000) across several seeds, so it
answers "at equal budget, who loses fewer decisions?" — the honest question.
`--single` reproduces the original two-transport report.

The interesting story is NOT "tallystone scores 1.0" — it is *which* axes each transport
loses, and at what token cost. The benchmark is designed to be able to FAIL
(see the negative-control tests in test_bench_tallystone.py).

Usage
-----
    python3 bench_tallystone.py                       # equal-budget sweep (default)
    python3 bench_tallystone.py --budgets 2000,8000 --seeds 42,7,13
    python3 bench_tallystone.py --single              # one comparison, 2 transports
    python3 bench_tallystone.py --single --mode audit --summary-mode history
    python3 bench_tallystone.py --single --with-llm   # optional real-model recall test
    python3 bench_tallystone.py --json                # machine-readable output
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import re
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

import tallystone as cb


# =============================================================================
# Scenario generation (deterministic)
# =============================================================================

# (topic, decision_template, rationale_template, tags)
_DECISION_POOL = [
    ("Language", "Use Python 3.12 for the service", "Team expertise and the ML ecosystem live in Python", ["language"]),
    ("Web framework", "Use FastAPI for the HTTP layer", "Async support and automatic OpenAPI docs reduce boilerplate", ["framework", "backend"]),
    ("Datastore", "Use PostgreSQL as the primary store", "Strong transactional guarantees for financial records", ["database"]),
    ("Cache", "Use Redis for the read-through cache", "Sub-millisecond reads and TTL eviction cover our latency budget", ["cache"]),
    ("Auth", "Use short-lived JWTs with refresh rotation", "Stateless verification scales horizontally without sticky sessions", ["auth", "security"]),
    ("Password hashing", "Use Argon2id for password hashing", "Memory-hard; resists GPU cracking better than bcrypt", ["auth", "security"]),
    ("Queue", "Use Celery for background jobs", "Mature retry and scheduling primitives we already operate", ["queue", "backend"]),
    ("Container runtime", "Use Docker with a distroless base image", "Smaller attack surface and faster cold starts", ["infra", "security"]),
    ("Orchestration", "Use Kubernetes for deployment", "Declarative rollout and horizontal autoscaling out of the box", ["infra"]),
    ("Observability", "Use OpenTelemetry for tracing", "Vendor-neutral instrumentation avoids lock-in", ["observability"]),
    ("Logging", "Use structured JSON logs", "Machine-parseable, ready for the log pipeline without regex", ["observability"]),
    ("API style", "Use REST with cursor pagination", "Simpler for external partners than GraphQL", ["api"]),
    ("Testing", "Use pytest with fixtures", "Concise fixtures and parametrization speed up suite growth", ["testing"]),
    ("Type safety", "Enforce mypy in strict mode", "Caught several production-class bugs during prototyping", ["quality"]),
    ("Formatting", "Use ruff for lint and format", "One fast tool replaces flake8 + isort + black", ["quality"]),
    ("Frontend", "Use React with TypeScript", "Type-safe component contracts across the team", ["frontend"]),
    ("State management", "Use React Query for server state", "Caching, retries and background refetch come for free", ["frontend"]),
    ("CI", "Use GitHub Actions for CI", "Co-located with the repo and simple matrix builds", ["ci"]),
    ("Secrets", "Load secrets from Vault at runtime", "No long-lived credentials baked into images", ["security", "infra"]),
    ("Rate limiting", "Use a token-bucket limiter at the gateway", "Smooths bursts without throttling steady clients", ["api", "security"]),
    ("Schema migration", "Use Alembic for migrations", "Autogeneration plus explicit review of each revision", ["database"]),
    ("Feature flags", "Use a homegrown flag service", "Avoids a hard dependency for a handful of toggles", ["infra"]),
    ("Email", "Use SES for transactional email", "Predictable pricing and delivery reputation", ["integration"]),
    ("Search", "Use Postgres full-text search first", "Avoid running Elasticsearch until relevance demands it", ["search"]),
]

_CONSTRAINT_POOL = [
    ("All user data must remain within the EU region", "compliance", "critical"),
    ("The service must run fully offline in air-gapped installs", "architecture", "critical"),
    ("No PII may be written to application logs", "security", "high"),
    ("All endpoints must be authenticated unless explicitly public", "security", "high"),
    ("Database migrations must be reversible", "architecture", "high"),
    ("Public API responses must stay under 200ms p95", "performance", "medium"),
    ("Every new module must ship with unit tests", "quality", "high"),
    ("Dependencies must be pinned to exact versions", "supply_chain", "high"),
    ("No GPL-licensed dependencies in the core service", "legal", "medium"),
    ("Secrets must never be committed to the repository", "security", "critical"),
    ("The build must be reproducible from a clean checkout", "build", "high"),
]

_PENDING_POOL = [
    "Implement refresh-token rotation endpoint",
    "Add cursor pagination to /v1/orders",
    "Backfill migration for the new invoices table",
    "Wire OpenTelemetry exporters into staging",
    "Write contract tests for the partner API",
    "Harden the rate limiter against clock skew",
    "Document the incident runbook",
]

_OPEN_QUESTIONS = [
    "Do we need per-tenant encryption keys?",
    "Is 200ms p95 achievable with full-text search enabled?",
]

_UNCERTAINTY = [
    "Refresh-token rotation details are not finalized",
    "Vault HA topology is still undecided",
]


@dataclass
class Scenario:
    """A deterministic, self-contained project state to hand off."""
    scope: str
    seed: int
    project: dict
    decisions: list[dict]        # each: key,title,decision,rationale,alternatives,tags,evidence,superseded,superseded_by
    constraints: list[dict]      # each: constraint,category,severity,source
    pending: list[str]
    open_questions: list[str]
    uncertainty: list[str]
    planted_conflicts: list[list[str]]  # list of [decision_key, decision_key]

    def to_dict(self) -> dict:
        return asdict(self)


def generate_scenario(
    seed: int = 42,
    n_decisions: int = 20,
    n_constraints: int = 10,
    n_pending: int = 5,
    scope: str = "bench-project",
) -> Scenario:
    """Build a reproducible project scenario.

    The pool has more entries than the default counts, so a larger request
    simply draws more unique topics. Every string embeds a stable serial number
    so recall checks cannot accidentally match on generic wording.
    """
    rng = random.Random(seed)

    decisions: list[dict] = []
    topics = list(_DECISION_POOL)
    rng.shuffle(topics)
    if n_decisions > len(topics):
        # Extend deterministically if a caller asks for more than the pool holds.
        for i in range(n_decisions - len(topics)):
            base = topics[i % len(topics)]
            topics.append((f"{base[0]} (rev {i + 1})", f"{base[1]} — variant {i + 1}",
                           f"{base[2]} — variant {i + 1}", base[3]))

    for idx in range(n_decisions):
        topic, decision, rationale, tags = topics[idx]
        key = f"D{idx + 1:02d}"
        # Unique, checkable serial marker embedded in the decision text.
        decision_text = f"[{key}] {decision} (spec {key})"
        rationale_text = f"[{key}] {rationale} (rationale {key})"
        evidence = [
            {"id": f"ev-{key}-1", "kind": "file", "locator": f"docs/adr/{key.lower()}.md",
             "description": f"ADR for {topic}", "verified": True},
            {"id": f"ev-{key}-2", "kind": "commit", "locator": f"abc{idx:04d}",
             "description": f"Commit implementing {topic}", "verified": True},
        ]
        alternatives = [
            {"option": f"alternative-A-{key}", "reason_rejected": f"rejected for {key} due to cost"},
            {"option": f"alternative-B-{key}", "reason_rejected": f"rejected for {key} due to complexity"},
        ]
        decisions.append({
            "key": key,
            "title": f"{topic} choice",
            "decision": decision_text,
            "rationale": rationale_text,
            "alternatives": alternatives,
            "tags": tags,
            "evidence": evidence,
            "superseded": False,
            "superseded_by": "",
        })

    # Plant supersessions: later decisions that replace earlier ones on the same tag.
    n_supersede = max(1, n_decisions // 10)  # ~2 for 20 decisions
    supersede_targets = decisions[:n_supersede]
    for t in supersede_targets:
        successor_key = f"S{t['key']}"
        successor = {
            "key": successor_key,
            "title": f"Revision of {t['title']}",
            "decision": f"[{successor_key}] Supersede {t['key']}: adopt a revised approach for {t['tags'][0]} (spec {successor_key})",
            "rationale": f"[{successor_key}] The original {t['key']} approach was reversed after the load test (rationale {successor_key})",
            "alternatives": [],
            "tags": list(t["tags"]),
            "evidence": [
                {"id": f"ev-{successor_key}-1", "kind": "test", "locator": f"tests/test_{t['tags'][0]}_rev.py",
                 "description": "Load test that forced the revision", "verified": True},
            ],
            "superseded": False,
            "superseded_by": "",
        }
        t["superseded"] = True
        t["superseded_by"] = successor_key
        decisions.append(successor)

    # Plant conflicts: two ACTIVE decisions sharing a tag, both accepted, different text.
    # Pick indices past the superseded block so we never undo a supersession.
    conflict_pairs: list[list[str]] = []
    non_superseded = [d for d in decisions if not d["superseded"]]
    if len(non_superseded) >= 3:
        a = non_superseded[0]
        b = non_superseded[2]
        a["tags"] = list(a["tags"]) + ["bench-conflict"]
        b["tags"] = list(b["tags"]) + ["bench-conflict"]
        conflict_pairs.append([a["key"], b["key"]])

    constraints = []
    for idx in range(n_constraints):
        constraint, category, severity = _CONSTRAINT_POOL[idx % len(_CONSTRAINT_POOL)]
        constraints.append({
            "constraint": f"{constraint} (rule {idx + 1:02d})",
            "category": category,
            "severity": severity,
            "source": "user",
        })

    pending = [f"{p} (task {i + 1:02d})" for i, p in enumerate(_PENDING_POOL[:n_pending])]

    project = {
        "name": "TaskFlow API",
        "purpose": "Multi-tenant task orchestration backend with partner integrations",
        "scope": scope,
        "tech_stack": ["Python", "FastAPI", "PostgreSQL", "Redis"],
        "repositories": ["/repos/taskflow-api"],
        "boundaries": ["EU-only data residency", "no third-party analytics"],
    }

    return Scenario(
        scope=scope,
        seed=seed,
        project=project,
        decisions=decisions,
        constraints=constraints,
        pending=pending,
        open_questions=list(_OPEN_QUESTIONS),
        uncertainty=list(_UNCERTAINTY),
        planted_conflicts=conflict_pairs,
    )


# =============================================================================
# Building records + transports
# =============================================================================

def build_records(scenario: Scenario, agent: str = "source-agent") -> list[cb.ContextRecord]:
    """Materialize the scenario as canonical tallystone records (in memory)."""
    records: list[cb.ContextRecord] = []
    p = scenario.project
    records.append(cb.create_record(
        cb.RecordKind.PROJECT_CONTEXT, project_scope=scenario.scope, created_by=agent,
        name=p["name"], purpose=p["purpose"], scope=scenario.scope,
        tech_stack=list(p["tech_stack"]), repositories=list(p["repositories"]),
        boundaries=list(p["boundaries"]),
    ))

    key_to_id: dict[str, str] = {}
    decision_records: list[cb.DecisionRecord] = []
    for d in scenario.decisions:
        ev = [cb.EvidenceReference(**e) for e in d["evidence"]]
        rec = cb.create_record(
            cb.RecordKind.DECISION_RECORD, project_scope=scenario.scope, created_by=agent,
            title=d["title"], decision=d["decision"], rationale=d["rationale"],
            alternatives=list(d["alternatives"]), outcome="accepted",
            tags=list(d["tags"]), evidence=ev,
            status=cb.VerificationStatus.VERIFIED,
        )
        key_to_id[d["key"]] = rec.id
        decision_records.append(rec)

    # Wire supersession links + status now that all ids exist.
    for d, rec in zip(scenario.decisions, decision_records):
        if d["superseded"] and d["superseded_by"]:
            rec.status = cb.VerificationStatus.SUPERSEDED
            rec.superseded_by = [key_to_id[d["superseded_by"]]]
        if d["key"].startswith("S") and d["key"][1:] in key_to_id:
            rec.supersedes = [key_to_id[d["key"][1:]]]

    records.extend(decision_records)

    for c in scenario.constraints:
        records.append(cb.create_record(
            cb.RecordKind.CONSTRAINT_RECORD, project_scope=scenario.scope, created_by=agent,
            constraint=c["constraint"], category=c["category"],
            severity=c["severity"], source=c["source"],
            status=cb.VerificationStatus.VERIFIED,
        ))

    records.append(cb.create_record(
        cb.RecordKind.WORKING_STATE, project_scope=scenario.scope, created_by=agent,
        active_task=scenario.pending[0] if scenario.pending else "n/a",
        state="in_progress",
        blockers=[],
        next_action=scenario.pending[1] if len(scenario.pending) > 1 else "n/a",
        progress={"completed": ["Repo scaffolded", "CI green"], "remaining": list(scenario.pending)},
    ))
    return records


def build_context_package(scenario: Scenario, records: list[cb.ContextRecord],
                          mode: str = "compact") -> cb.ContextPackage:
    """Build the handoff package.

    mode mirrors the product's `mem.py context handoff --history` flag:

      * "current" — current decisions only, no change history (the OLD default)
      * "compact" — current decisions + compact change history (NEW DEFAULT)
      * "audit"   — every decision record, superseded ones included, no compaction
    """
    project_ctx = next((r for r in records if isinstance(r, cb.ProjectContext)), None)
    all_decisions = [r for r in records if isinstance(r, cb.DecisionRecord)]
    all_constraints = [r for r in records if isinstance(r, cb.ConstraintRecord)]

    active = [d for d in all_decisions
              if d.status != cb.VerificationStatus.SUPERSEDED and not d.superseded_by]
    if mode == "audit":
        decisions = all_decisions
        history: list[cb.SupersessionEntry] = []
    else:
        decisions = active
        history = cb.build_supersession_history(all_decisions) if mode == "compact" else []

    constraints = [c for c in all_constraints if c.status != cb.VerificationStatus.SUPERSEDED]
    working_state = next((r for r in records if isinstance(r, cb.WorkingState)), None)

    evidence: list[cb.EvidenceReference] = []
    for r in decisions + constraints + ([working_state] if working_state else []):
        evidence.extend(r.evidence)

    return cb.ContextPackage(
        project_context=project_ctx,
        decisions=decisions,
        constraints=constraints,
        supersession_history=history,
        working_state=working_state,
        evidence=evidence,
        open_questions=list(scenario.open_questions),
        uncertainty=list(scenario.uncertainty),
        created_by="source-agent",
    )


def transport_tallystone(scenario: Scenario, mode: str = "compact",
                             budget: int | None = None, wire: str = "full") -> str:
    """Return the tallystone transport text (the handoff JSON).

    wire="full"    — the canonical, indented, verbose-key export (to_json).
    wire="compact" — the compact wire encoding (to_wire_json): same facts, no
                     indentation, default/empty fields elided, short keys. The
                     token budget (when given) is measured in the same encoding.
    """
    records = build_records(scenario)
    package = build_context_package(scenario, records, mode=mode)
    if budget:
        package = cb.fit_package_to_budget(package, budget, wire=wire)
    return package.to_wire_json() if wire == "compact" else package.to_json()


def _fill(lines: list[str], budget_tokens: int | None) -> str:
    """Greedily include lines until the token budget is reached (first line always)."""
    out, total = [], 0
    for line in lines:
        candidate = total + len(line) + 1
        if budget_tokens and out and candidate // 4 > budget_tokens:
            continue
        out.append(line)
        total = candidate
    return "\n".join(out)


def transport_chat_summary(scenario: Scenario, summary_mode: str = "terse",
                           budget: int | None = None) -> str:
    """Return a chat-summary transport.

    terse   : current decisions + constraints + next steps (no rationale/history)
    verbose : the above PLUS every decision's rationale
    history : verbose PLUS a "what changed" section (the strongest baseline —
              a summary that DOES narrate reversals, to keep the comparison fair)
    """
    include_rationale = summary_mode in ("verbose", "history")
    include_history = summary_mode == "history"
    active = [d for d in scenario.decisions if not d["superseded"]]

    lines = [
        f"# Session Summary: {scenario.project['name']}",
        f"",
        f"Purpose: {scenario.project['purpose']}",
        f"",
        "## Decisions we made",
    ]
    for d in active:
        line = f"- {d['title']}: {d['decision']}"
        if include_rationale:
            line += f" \u2014 because {d['rationale']}"
        lines.append(line)

    if include_history:
        lines.append("")
        lines.append("## What changed")
        for d in scenario.decisions:
            if not d["superseded"]:
                continue
            repl = next((x for x in scenario.decisions if x["key"] == d["superseded_by"]), None)
            if repl:
                lines.append(f"- Changed from '{d['decision']}' to '{repl['decision']}': {repl['rationale']}")

    lines.append("")
    lines.append("## Constraints")
    for c in scenario.constraints:
        lines.append(f"- {c['constraint']}")
    lines.append("")
    lines.append("## Next steps")
    for t in scenario.pending:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("## Open questions")
    for q in scenario.open_questions:
        lines.append(f"- {q}")
    lines.append("")

    return _fill(lines, budget)


# =============================================================================
# Scoring
# =============================================================================

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _present(haystack: str, needle: str) -> bool:
    needle = _norm(needle)
    return bool(needle) and needle in _norm(haystack)


def _present_prefix(haystack: str, needle: str, n: int = 60) -> bool:
    """True if the first n chars of `needle` survive (tolerates compaction)."""
    return _present(haystack, (needle or "")[:n])


@dataclass
class Metrics:
    decision_recall: float = 0.0
    rationale_preservation: float = 0.0
    constraint_recall: float = 0.0
    evidence_provenance: float = 0.0
    change_history: float = 0.0
    conflict_visibility: float = 0.0
    pending_task_recall: float = 0.0
    critical_fact_preservation: float = 0.0
    tokens: int = 0

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _ratio(present: int, total: int) -> float:
    return (present / total) if total else 1.0


def evaluate(scenario: Scenario, transport_text: str, records: list[cb.ContextRecord]) -> Metrics:
    """Score how much critical context survives in a transport."""
    active = [d for d in scenario.decisions if not d["superseded"]]
    superseded = [d for d in scenario.decisions if d["superseded"]]

    decision_hits = sum(1 for d in active if _present(transport_text, d["decision"]))
    rationale_hits = sum(1 for d in active if _present(transport_text, d["rationale"]))
    constraint_hits = sum(1 for c in scenario.constraints if _present(transport_text, c["constraint"]))
    ev_locators = [e["locator"] for d in scenario.decisions for e in d["evidence"]]
    evidence_hits = sum(1 for loc in ev_locators if _present(transport_text, loc))
    pending_hits = sum(1 for t in scenario.pending if _present(transport_text, t))

    # change_history: for each superseded decision, both the old decision and its
    # replacement must be recoverable (so a target agent can see the project
    # changed its mind, and what it changed to).
    history_hits = 0
    for d in superseded:
        repl = next((x for x in scenario.decisions if x["key"] == d["superseded_by"]), None)
        if repl and _present_prefix(transport_text, d["decision"]) and _present_prefix(transport_text, repl["decision"]):
            history_hits += 1

    # conflict_visibility: a planted contradiction stays *detectable* only if the
    # transport preserves BOTH sides AND the shared structured signal (the common
    # tag) that lets an automated detector pair them. A flat summary keeps the
    # two statements but drops every tag, so the conflict is no longer machine-
    # detectable. (The tallystone package also feeds cb.detect_conflicts; this metric
    # isolates the information the *transport* retained.)
    conflicts_detected = 0
    conflict_tag = "bench-conflict"
    for pair in scenario.planted_conflicts:
        pair_decisions = [d for d in scenario.decisions if d["key"] in pair]
        both_present = all(_present(transport_text, d["decision"]) for d in pair_decisions)
        tag_present = _present(transport_text, conflict_tag)
        if both_present and tag_present:
            conflicts_detected += 1

    m = Metrics(
        decision_recall=_ratio(decision_hits, len(active)),
        rationale_preservation=_ratio(rationale_hits, len(active)),
        constraint_recall=_ratio(constraint_hits, len(scenario.constraints)),
        evidence_provenance=_ratio(evidence_hits, len(ev_locators)),
        change_history=_ratio(history_hits, len(superseded)),
        conflict_visibility=_ratio(conflicts_detected, len(scenario.planted_conflicts)),
        pending_task_recall=_ratio(pending_hits, len(scenario.pending)),
        tokens=len(transport_text) // 4,
    )
    axes = [
        m.decision_recall, m.rationale_preservation, m.constraint_recall,
        m.evidence_provenance, m.change_history, m.conflict_visibility,
        m.pending_task_recall,
    ]
    m.critical_fact_preservation = sum(axes) / len(axes)
    return m


# =============================================================================
# Optional: real LLM agent-simulation recall test
# =============================================================================

def llm_available(base_url: str = "http://localhost:11434", timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def ask_llm(prompt: str, model: str, base_url: str = "http://localhost:11434",
            timeout: float = 120.0) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.0}}).encode()
    req = urllib.request.Request(f"{base_url}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("response", "")


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "than", "then",
    "they", "them", "their", "because", "which", "when", "where", "would", "could",
    "should", "have", "has", "had", "are", "was", "were", "will", "been", "being",
    "about", "over", "under", "also", "more", "most", "such", "only", "does", "not",
    "but", "its", "our", "your", "than", "then", "you", "the", "a", "an", "of",
    "to", "in", "on", "at", "by", "is", "it", "as", "we", "be", "or", "if", "no",
}


def _keywords(text: str, k: int = 6) -> list[str]:
    """Distinctive content words from a ground-truth string, for overlap scoring."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]{4,}", text.lower())
    uniq, seen = [], set()
    for w in words:
        if w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        uniq.append(w)
    return uniq[:k]


def build_llm_queries(scenario: Scenario, k_decisions: int = 3) -> list[dict]:
    """Questions whose answers require the rationale/history a summary drops."""
    queries = []
    for d in [x for x in scenario.decisions if not x["superseded"]][:k_decisions]:
        queries.append({
            "question": f"What was the rationale for the decision titled '{d['title']}'? Answer in one sentence.",
            "keywords": _keywords(d["rationale"]),
            "min_overlap": 0.5,
            "kind": "rationale",
        })
    queries.append({
        "question": "List the pending tasks.",
        "keywords": _keywords(scenario.pending[0]) if scenario.pending else [],
        "min_overlap": 0.5,
        "kind": "pending",
    })
    return queries


def _grade(answer: str, keywords: list[str], min_overlap: float) -> bool:
    if not keywords:
        return False
    ans = _norm(answer)
    hits = sum(1 for kw in keywords if kw in ans)
    return (hits / len(keywords)) >= min_overlap


def run_llm_eval(scenario: Scenario, transport_text: str, model: str) -> dict:
    queries = build_llm_queries(scenario)
    hits = 0
    answers = []
    for q in queries:
        prompt = (
            "You are resuming a software project from the context below. "
            "Answer ONLY from this context.\n\n"
            f"=== CONTEXT ===\n{transport_text}\n=== END CONTEXT ===\n\n"
            f"Question: {q['question']}"
        )
        try:
            ans = ask_llm(prompt, model=model)
        except Exception as e:  # pragma: no cover - env dependent
            return {"status": "error", "error": str(e), "accuracy": None}
        ok = _grade(ans, q["keywords"], q["min_overlap"])
        hits += int(ok)
        answers.append({"question": q["question"], "kind": q["kind"], "correct": ok,
                        "answer": ans[:300]})
    return {"status": "ok", "accuracy": hits / len(queries), "n": len(queries), "answers": answers}


# =============================================================================
# Report
# =============================================================================

_METRIC_ORDER = [
    ("decision_recall", "Decision recall"),
    ("rationale_preservation", "Rationale preservation"),
    ("constraint_recall", "Constraint recall"),
    ("evidence_provenance", "Evidence provenance"),
    ("change_history", "Change history"),
    ("conflict_visibility", "Conflict visibility"),
    ("pending_task_recall", "Pending task recall"),
    ("critical_fact_preservation", "CRITICAL FACT PRESERVATION"),
]


def run_benchmark(seed: int = 42, n_decisions: int = 20, n_constraints: int = 10,
                  n_pending: int = 5, summary_mode: str = "terse",
                  mode: str = "compact") -> dict:
    scenario = generate_scenario(seed=seed, n_decisions=n_decisions,
                                 n_constraints=n_constraints, n_pending=n_pending)
    records = build_records(scenario)

    transports = {
        "tallystone": transport_tallystone(scenario, mode=mode),
        "chat_summary": transport_chat_summary(scenario, summary_mode=summary_mode),
    }
    metrics = {name: evaluate(scenario, text, records) for name, text in transports.items()}

    ts_m = metrics["tallystone"]
    sm_m = metrics["chat_summary"]
    deltas = {k: round(getattr(ts_m, k) - getattr(sm_m, k), 4) for k, _ in _METRIC_ORDER}

    return {
        "meta": {
            "seed": seed,
            "n_decisions": n_decisions,
            "n_constraints": n_constraints,
            "n_pending": n_pending,
            "summary_mode": summary_mode,
            "mode": mode,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        "counts": {
            "active_decisions": len([d for d in scenario.decisions if not d["superseded"]]),
            "superseded_decisions": len([d for d in scenario.decisions if d["superseded"]]),
            "constraints": len(scenario.constraints),
            "pending": len(scenario.pending),
            "planted_conflicts": len(scenario.planted_conflicts),
        },
        "metrics": {name: m.to_dict() for name, m in metrics.items()},
        "deltas_tallystone_minus_summary": deltas,
    }


def print_report(result: dict) -> None:
    meta, counts = result["meta"], result["counts"]
    ts_m, sm_m = result["metrics"]["tallystone"], result["metrics"]["chat_summary"]

    print("=" * 74)
    print("  TALLYSTONE BENCHMARK  —  structured handoff vs. chat summary")
    print("=" * 74)
    print(f"  seed={meta['seed']}  decisions={meta['n_decisions']} "
          f"(active {counts['active_decisions']}, superseded {counts['superseded_decisions']})")
    print(f"  constraints={counts['constraints']}  pending={counts['pending']}  "
          f"planted_conflicts={counts['planted_conflicts']}")
    print(f"  summary_mode={meta['summary_mode']}  mode={meta['mode']}")
    print("-" * 74)
    print(f"  {'Metric':<30}{'Tallystone':>13}{'ChatSummary':>13}{'Delta':>10}")
    print("-" * 74)
    for key, label in _METRIC_ORDER:
        c, s = ts_m[key], sm_m[key]
        d = c - s
        flag = "  <-- tallystone" if d > 0.0001 else ("  <-- summary" if d < -0.0001 else "")
        print(f"  {label:<30}{c:>13.3f}{s:>13.3f}{d:>+10.3f}{flag}")
    print("-" * 74)
    print(f"  {'Transport tokens':<30}{ts_m['tokens']:>13}{sm_m['tokens']:>13}"
          f"{ts_m['tokens'] - sm_m['tokens']:>+10}")
    print("=" * 74)

    better = [k for k, _ in _METRIC_ORDER if ts_m[k] - sm_m[k] > 0.0001]
    worse = [k for k, _ in _METRIC_ORDER if ts_m[k] - sm_m[k] < -0.0001]
    print(f"  tallystone strictly better on {len(better)} metric(s); "
          f"worse on {len(worse)}.")
    if worse:
        print(f"  (summary wins: {', '.join(worse)})")


# =============================================================================
# Equal-budget, multi-seed sweep
# =============================================================================

# name -> callable(scenario, budget_tokens) -> transport text
# `ts_*`      = full (indented, verbose-key) JSON  — the "before" encoding.
# `ts_*_wire` = compact wire encoding               — the "after" encoding.
METHODS = {
    "ts_compact":       lambda sc, b: transport_tallystone(sc, mode="compact", budget=b),
    "ts_audit":         lambda sc, b: transport_tallystone(sc, mode="audit", budget=b),
    "ts_current":       lambda sc, b: transport_tallystone(sc, mode="current", budget=b),
    "ts_compact_wire":  lambda sc, b: transport_tallystone(sc, mode="compact", budget=b, wire="compact"),
    "ts_audit_wire":    lambda sc, b: transport_tallystone(sc, mode="audit", budget=b, wire="compact"),
    "ts_current_wire":  lambda sc, b: transport_tallystone(sc, mode="current", budget=b, wire="compact"),
    "sum_terse":        lambda sc, b: transport_chat_summary(sc, "terse", budget=b),
    "sum_verbose":      lambda sc, b: transport_chat_summary(sc, "verbose", budget=b),
    "sum_history":      lambda sc, b: transport_chat_summary(sc, "history", budget=b),
}

# Held-out scenario shapes, deliberately different from the tuned default
# (n_decisions=20, n_constraints=10, n_pending=5) so a serialization change
# cannot be tuned to the fixture. Reported separately (never merged).
HOLDOUT_CONFIGS = [
    {"n_decisions": 12, "n_constraints": 6, "n_pending": 3},
    {"n_decisions": 28, "n_constraints": 14, "n_pending": 8},
]

_SWEEP_AXES = [
    "critical_fact_preservation",
    "decision_recall",
    "rationale_preservation",
    "constraint_recall",
    "evidence_provenance",
    "change_history",
    "conflict_visibility",
    "pending_task_recall",
    "tokens",
]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_sweep(seeds: list[int], budgets: list[int], methods: list[str] | None = None,
              n_decisions: int = 20, n_constraints: int = 10, n_pending: int = 5) -> dict:
    """Run every method at every budget across every seed; aggregate means.

    This is the "same token budget, who loses fewer decisions?" experiment: each
    transport is greedily filled to the same budget, then scored.
    """
    methods = methods or list(METHODS)
    for m in methods:
        if m not in METHODS:
            raise ValueError(f"unknown method {m!r}; choose from {list(METHODS)}")

    agg: dict[int, dict[str, dict]] = {}
    for budget in budgets:
        agg[budget] = {}
        for name in methods:
            fn = METHODS[name]
            rows: list[Metrics] = []
            for seed in seeds:
                sc = generate_scenario(seed=seed, n_decisions=n_decisions,
                                       n_constraints=n_constraints, n_pending=n_pending)
                recs = build_records(sc)
                text = fn(sc, budget)
                rows.append(evaluate(sc, text, recs))
            agg[budget][name] = {ax: _mean([getattr(r, ax) for r in rows]) for ax in _SWEEP_AXES}

    return {
        "meta": {
            "seeds": seeds,
            "budgets": budgets,
            "methods": methods,
            "n_decisions": n_decisions,
            "n_constraints": n_constraints,
            "n_pending": n_pending,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        "budgets": budgets,
        "methods": methods,
        "agg": agg,
    }


def _grid(result: dict, axis: str, fmt: str = "{:.3f}") -> None:
    budgets = result["budgets"]
    methods = result["methods"]
    header = f"  {'method':<14}" + "".join(f"{b:>10}" for b in budgets)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name in methods:
        cells = "".join(fmt.format(result['agg'][b][name][axis]).rjust(10) for b in budgets)
        print(f"  {name:<14}{cells}")


def print_sweep_report(result: dict) -> None:
    m = result["meta"]
    print("=" * (14 + 10 * len(result["budgets"]) + 2))
    print("  EQUAL-BUDGET SWEEP  —  tallystone vs. rival summaries")
    print("=" * (14 + 10 * len(result["budgets"]) + 2))
    print(f"  seeds={m['seeds']}")
    print(f"  budgets (tokens)={m['budgets']}   decisions={m['n_decisions']} "
          f"constraints={m['n_constraints']} pending={m['n_pending']}")
    print()
    print("  critical_fact_preservation (mean over seeds):")
    _grid(result, "critical_fact_preservation")
    print()
    print("  change_history (mean over seeds):")
    _grid(result, "change_history")
    print()
    print("  rationale_preservation (mean over seeds):")
    _grid(result, "rationale_preservation")
    print()
    print("  avg transport tokens (mean over seeds):")
    _grid(result, "tokens", fmt="{:.0f}")
    print("=" * (14 + 10 * len(result["budgets"]) + 2))


# =============================================================================
# Token profile — where the tokens actually go
# =============================================================================

def _tok(obj) -> int:
    """Char/4 token estimate of a string (or of a compact JSON dump of an object)."""
    if isinstance(obj, str):
        return len(obj) // 4
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":"))) // 4


def profile_tokens(scenario: Scenario, mode: str = "compact") -> dict:
    """Break serialized token usage down by top-level field and encoding.

    Each field is measured with the *same* encoding as the whole document, so
    `serialization_overhead` (whole - sum of parts) is the genuine cost of
    braces, keys, commas, and indentation — exactly where the wire format wins.
    """
    records = build_records(scenario)
    package = build_context_package(scenario, records, mode=mode)
    full_dict = package.to_dict()
    wire_dict = package.to_wire_dict()

    full_total = len(package.to_json()) // 4
    wire_total = len(package.to_wire_json()) // 4
    full_fields = {k: len(json.dumps(v, ensure_ascii=False, indent=2)) // 4
                   for k, v in full_dict.items()}
    wire_fields = {k: _tok(v) for k, v in wire_dict.items()}

    return {
        "full_total": full_total,
        "wire_total": wire_total,
        "reduction_ratio": round(full_total / wire_total, 3) if wire_total else 0.0,
        "full_by_field": full_fields,
        "wire_by_field": wire_fields,
        "full_serialization_overhead": full_total - sum(full_fields.values()),
        "wire_serialization_overhead": wire_total - sum(wire_fields.values()),
    }


def print_profile(profile: dict) -> None:
    print("=" * 62)
    print("  TOKEN PROFILE  —  where the tokens go")
    print("=" * 62)
    print(f"  full = {profile['full_total']:>6} tokens")
    print(f"  wire = {profile['wire_total']:>6} tokens   (reduction x{profile['reduction_ratio']})")
    print(f"  serialization overhead: full={profile['full_serialization_overhead']}  "
          f"wire={profile['wire_serialization_overhead']}")
    print("  --- full, by top-level field ---")
    for k, v in sorted(profile["full_by_field"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<24}{v:>8}")
    print("  --- wire, by top-level field ---")
    for k, v in sorted(profile["wire_by_field"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<24}{v:>8}")
    print("=" * 62)


def run_holdout(seeds: list[int], budgets: list[int],
                methods: list[str] | None = None) -> dict:
    """Run the sweep over held-out scenario shapes; keep results separate."""
    results = []
    for cfg in HOLDOUT_CONFIGS:
        r = run_sweep(seeds=seeds, budgets=budgets, methods=methods, **cfg)
        r["holdout_config"] = cfg
        results.append(r)
    return {"meta": {"seeds": seeds, "budgets": budgets}, "holdout": results}


# =============================================================================
# CLI
# =============================================================================

def _csv_ints(s: str) -> list[int]:
    return [int(x) for x in s.replace(" ", "").split(",") if x]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="tallystone vs chat-summary benchmark")
    ap.add_argument("--decisions", type=int, default=20)
    ap.add_argument("--constraints", type=int, default=10)
    ap.add_argument("--pending", type=int, default=5)
    ap.add_argument("--seeds", default="42,7,13,101,2024",
                    help="comma-separated seeds for the equal-budget sweep")
    ap.add_argument("--budgets", default="1000,2000,4000,8000,16000",
                    help="comma-separated token budgets")
    ap.add_argument("--methods", default="",
                    help=f"comma-separated subset of {list(METHODS)} (default: all)")
    ap.add_argument("--single", action="store_true",
                    help="run the original single-budget report instead of the sweep")
    ap.add_argument("--seed", type=int, default=42, help="seed for --single")
    ap.add_argument("--summary-mode", choices=["terse", "verbose", "history"], default="terse")
    ap.add_argument("--mode", choices=["current", "compact", "audit"], default="compact")
    ap.add_argument("--with-llm", action="store_true", help="(with --single) optional real-model recall test")
    ap.add_argument("--llm-model", default="qwen2.5:7b-instruct")
    ap.add_argument("--json", action="store_true", help="print raw JSON result")
    ap.add_argument("--out", default="bench_results", help="dir for JSON result ('' disables)")
    ap.add_argument("--min-advantage", type=float, default=0.0,
                    help="(--single) exit non-zero unless tallystone beats summary by this much")
    ap.add_argument("--profile", action="store_true",
                    help="print the token profile (by field and encoding) and exit")
    ap.add_argument("--holdout", action="store_true",
                    help="run the sweep over held-out scenario shapes and exit")
    args = ap.parse_args(argv)

    if args.profile:
        scenario = generate_scenario(args.seed, args.decisions, args.constraints, args.pending)
        prof = profile_tokens(scenario, mode=args.mode)
        if args.json:
            print(json.dumps(prof, indent=2))
        else:
            print_profile(prof)
        return 0

    if args.single:
        result = run_benchmark(seed=args.seed, n_decisions=args.decisions,
                               n_constraints=args.constraints, n_pending=args.pending,
                               summary_mode=args.summary_mode, mode=args.mode)
        if args.with_llm:
            scenario = generate_scenario(args.seed, args.decisions, args.constraints, args.pending)
            if llm_available():
                ts_text = transport_tallystone(scenario, mode=args.mode)
                sm_text = transport_chat_summary(scenario, summary_mode=args.summary_mode)
                result["llm"] = {
                    "model": args.llm_model,
                    "tallystone": run_llm_eval(scenario, ts_text, args.llm_model),
                    "chat_summary": run_llm_eval(scenario, sm_text, args.llm_model),
                }
            else:
                result["llm"] = {"status": "NOT_RUN", "reason": "no Ollama server reachable"}

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_report(result)
            if "llm" in result:
                llm = result["llm"]
                if llm.get("status") == "NOT_RUN":
                    print(f"\n  LLM recall test: NOT_RUN ({llm['reason']})")
                elif llm.get("status") == "error":
                    print(f"\n  LLM recall test: ERROR ({llm['error']})")
                else:
                    print(f"\n  LLM recall accuracy (model={llm['model']}): "
                          f"ts={llm['tallystone'].get('accuracy'):.2f} "
                          f"summary={llm['chat_summary'].get('accuracy'):.2f}")
        adv = result["deltas_tallystone_minus_summary"]["critical_fact_preservation"]
        rc = 0 if adv >= args.min_advantage else 1
    elif args.holdout:
        methods = [m for m in args.methods.split(",") if m] or None
        result = run_holdout(seeds=_csv_ints(args.seeds), budgets=_csv_ints(args.budgets),
                             methods=methods)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for r in result["holdout"]:
                print(f"\n### HOLDOUT config: {r['holdout_config']}")
                print_sweep_report(r)
        rc = 0
    else:
        methods = [m for m in args.methods.split(",") if m] or None
        result = run_sweep(seeds=_csv_ints(args.seeds), budgets=_csv_ints(args.budgets),
                           methods=methods, n_decisions=args.decisions,
                           n_constraints=args.constraints, n_pending=args.pending)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_sweep_report(result)
        rc = 0

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"bench_{stamp}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
