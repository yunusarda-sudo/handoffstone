#!/usr/bin/env python3
"""Handoffstone M4: dependency-free, manual stdio MCP bridge (prototype).

Requires Handoffstone P0 reliability core. No database migration, services, or
agent calls. Configure HANDOFFSTONE_HOME and HANDOFFSTONE_ALLOWED_REPO_ROOT.
Do not enable against untrusted MCP clients: the server grants scoped read/write.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import handoffstone as hs

PROTOCOL = "2025-06-18"
SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_LINE = 2 * 1024 * 1024


class ToolFault(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _required_core() -> None:
    # Old public main swallowed write/load failures; refusing it is deliberate.
    required = ("StoreWriteError", "StoreCorruptionError", "StoreUnavailableError",
                "UnsafeContentError", "InvalidScopeError", "VerificationError")
    if any(not hasattr(hs, name) for name in required):
        raise ToolFault("p0_reliability_core_required")
    store = os.environ.get("HANDOFFSTONE_HOME", "")
    root = os.environ.get("HANDOFFSTONE_ALLOWED_REPO_ROOT", "")
    if not store or not root or not Path(store).is_absolute() or not Path(root).is_absolute():
        raise ToolFault("explicit_store_and_allowed_repo_root_required")
    if Path(hs.HANDOFFSTONE_DIR).resolve() != Path(store).resolve():
        raise ToolFault("store_directory_mismatch")


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not SCOPE_RE.fullmatch(value):
        raise ToolFault("invalid_project_scope")
    return value


def _git(path: Path, *args: str) -> str:
    try:
        cp = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                            text=True, timeout=5, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        raise ToolFault("git_unavailable") from None
    if cp.returncode:
        raise ToolFault("git_probe_failed")
    return cp.stdout.strip()


def _worktree_digest(root: Path) -> str:
    # dirty_state + untracked files included; sorted for deterministic hashing.
    cp = subprocess.run(["git", "-C", str(root), "status", "--porcelain",
                         "-uall", "--no-renames"], capture_output=True,
                        text=True, timeout=5, check=False)
    if cp.returncode:
        raise ToolFault("git_probe_failed")
    lines = sorted(cp.stdout.splitlines())
    return hashlib.sha256("\n".join(lines).encode("utf-8", "surrogatepass")).hexdigest()


def _repo(path: Any) -> dict:
    if not isinstance(path, str) or not path.strip():
        raise ToolFault("repo_path_required")
    allowed = Path(os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"]).resolve(strict=True)
    p = Path(path).resolve(strict=True)
    if not p.is_relative_to(allowed):
        raise ToolFault("repo_outside_allowed_root")
    root = Path(_git(p, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if not root.is_relative_to(allowed):
        raise ToolFault("git_root_outside_allowed_root")
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    dirty = _worktree_digest(root)
    return {"root": str(root), "branch": branch, "head": head, "dirty_digest": dirty}


def _string(obj: dict, field: str, required: bool = True) -> str:
    v = obj.get(field, "")
    if not isinstance(v, str) or (required and not v.strip()):
        raise ToolFault("invalid_" + field)
    if len(v) > 30000:
        raise ToolFault("field_too_large")
    return v


def _guard_data(obj: Any) -> None:
    # Scan every string, including dict keys; P0 core must also enforce its
    # central secret rejection at persistence. Regex scans are not infallible.
    if isinstance(obj, str):
        if hs.detect_secrets(obj):
            raise ToolFault("unsafe_content_rejected")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _guard_data(k)
            _guard_data(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _guard_data(v)


def _evidence(items: Any, repo: dict) -> list:
    if not isinstance(items, list) or len(items) > 30:
        raise ToolFault("invalid_evidence")
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ToolFault("invalid_evidence")
        kind, loc = _string(item, "kind"), _string(item, "locator")
        if kind not in {"file", "commit", "test", "url", "memory", "conversation"}:
            raise ToolFault("invalid_evidence_kind")
        verified = _verify(kind, loc, repo)
        out.append(hs.EvidenceReference(
            id=str(item.get("id") or f"evidence-{i}"), kind=kind,
            locator=loc, description=_string(item, "description", False),
            verified=verified))
    return out


def _verify(kind: str, locator: str, repo: dict) -> bool:
    root = Path(repo["root"])
    if kind == "file":
        candidate = (root / locator).resolve()
        return candidate.is_relative_to(root) and candidate.is_file()
    if kind == "commit" and re.fullmatch(r"[a-fA-F0-9]{7,40}", locator):
        try:
            _git(root, "cat-file", "-e", locator + "^{commit}")
            return True
        except ToolFault:
            return False
    return False  # Never trust a client-supplied verified:true for tests/URLs.


def _refresh_evidence(records: list, repo: dict) -> list:
    safe = copy.deepcopy(records)
    for rec in safe:
        refs = getattr(rec, "evidence", [])
        checked = []
        for e in refs:
            e.verified = _verify(e.kind, e.locator, repo)
            checked.append(e.verified)
        if str(getattr(rec, "status", "")) in ("verified", "VerificationStatus.VERIFIED"):
            if not checked or not any(checked):
                rec.status = hs.VerificationStatus.UNVERIFIED
    return safe


def _load(scope: str) -> list:
    # Requires P0 load_records to distinguish corruption from no records.
    return hs.load_records(scope)


def _snapshot_state(cp: Any, scope: str):
    if cp is None:
        return None
    s = cp.snapshot
    if not isinstance(s, dict):
        raise ToolFault("malformed_checkpoint_snapshot")
    return hs.WorkingState(
        id="checkpoint-state-" + cp.id, kind=hs.RecordKind.WORKING_STATE,
        project_scope=scope, created_at=cp.created_at, created_by=cp.created_by,
        active_task=s.get("active_task", ""), next_action=s.get("next_action", ""),
        blockers=s.get("blockers", []), progress=s.get("progress", {}),
        state=s.get("state", "in_progress"),
        status=hs.VerificationStatus.UNVERIFIED)


def _assemble(args: dict):
    scope, repo = _scope(args.get("project_scope")), _repo(args.get("repo_path"))
    rows = _load(scope)
    checkpoints = [r for r in rows if r.kind == hs.RecordKind.CONTEXT_CHECKPOINT]
    if not checkpoints:
        return {"state": "empty" if not rows else "missing_checkpoint",
                "ready": False, "scope": scope, "context": None}, None
    cp = max(checkpoints, key=lambda r: (r.created_at, r.id))
    if not isinstance(cp.snapshot, dict):
        raise ToolFault("malformed_checkpoint_snapshot")
    previous = cp.snapshot.get("_handoffstone_repo")
    if not isinstance(previous, dict) or previous.get("root") != repo["root"]:
        return {"state": "project_mismatch", "ready": False,
                "scope": scope, "context": None}, None
    if previous.get("branch") != repo["branch"]:
        return {"state": "stale_branch", "ready": False,
                "scope": scope, "context": None}, None
    if previous.get("head") != repo["head"]:
        return {"state": "stale_head", "ready": False,
                "scope": scope, "context": None}, None
    recorded_digest = previous.get("dirty_digest")
    if recorded_digest and recorded_digest != repo["dirty_digest"]:
        return {"state": "worktree_changed", "ready": False,
                "scope": scope, "context": None, "dirty": True}, None
    decisions_all = _refresh_evidence(
        [r for r in rows if r.kind == hs.RecordKind.DECISION_RECORD], repo)
    active = [d for d in decisions_all if d.status != hs.VerificationStatus.SUPERSEDED
              and not getattr(d, "superseded_by", [])]
    constraints = _refresh_evidence(
        [r for r in rows if r.kind == hs.RecordKind.CONSTRAINT_RECORD], repo)
    context = hs.ContextPackage(
        decisions=active, constraints=constraints,
        supersession_history=hs.build_supersession_history(decisions_all),
        working_state=_snapshot_state(cp, scope),
        created_by="handoffstone-mcp")
    budget = args.get("max_tokens", 6000)
    if type(budget) is not int or not 500 <= budget <= 30000:
        raise ToolFault("invalid_token_budget")
    trimmed = hs.fit_package_to_budget(context, budget, wire="compact")
    serialized = trimmed.to_wire_json()
    if len(serialized) // 4 > budget:
        return {"state": "budget_exceeded", "ready": False,
                "scope": scope, "context": None}, None
    return {"state": "ready", "ready": True, "scope": scope,
            "repo": repo, "checkpoint_id": cp.id,
            "snapshot": {k: v for k, v in cp.snapshot.items() if k != "_handoffstone_repo"},
            "included_decisions": len(trimmed.decisions),
            "omitted_decisions": len(active) - len(trimmed.decisions),
            "context": trimmed.to_dict()}, trimmed


def _checkpoint(args: dict) -> dict:
    scope, repo = _scope(args.get("project_scope")), _repo(args.get("repo_path"))
    agent = _string(args, "agent")
    label = _string(args, "label")
    snap = args.get("snapshot")
    if not isinstance(snap, dict):
        raise ToolFault("snapshot_object_required")
    if "_handoffstone_repo" in snap:
        raise ToolFault("reserved_snapshot_field")
    for field in ("active_task", "next_action"):
        if field not in snap or not isinstance(snap[field], str):
            raise ToolFault("invalid_snapshot_" + field)
    evidence = _evidence(args.get("evidence", []), repo)
    # Optional decision capture. Not transactionally atomic with checkpoint;
    # failure must report a partial-write risk, never success.
    decisions = args.get("decisions", [])
    if not isinstance(decisions, list) or len(decisions) > 20:
        raise ToolFault("invalid_decisions")
    for d in decisions:
        if not isinstance(d, dict):
            raise ToolFault("invalid_decisions")
        _string(d, "title"); _string(d, "decision"); _string(d, "rationale")
        if d.get("status", "agent_inferred") not in {"agent_inferred", "user_asserted", "verified"}:
            raise ToolFault("invalid_verification_status")
        # A file or Git object existing is NOT proof it supports a claim.
        # This bridge cannot promote decisions to verified without an independent
        # content-aware verifier, so reject rather than launder trust.
        if d.get("status") == "verified":
            raise ToolFault("independent_verification_required")
        if not isinstance(d.get("supersedes", []), list):
            raise ToolFault("invalid_supersedes")
    # A scope already tied to another repository/branch cannot be reused.
    # Without this check a newer checkpoint could expose an older repo's decisions.
    for existing in _load(scope):
        if existing.kind == hs.RecordKind.CONTEXT_CHECKPOINT:
            bound = existing.snapshot.get("_handoffstone_repo") if isinstance(existing.snapshot, dict) else None
            if not isinstance(bound, dict) or bound.get("root") != repo["root"] or bound.get("branch") != repo["branch"]:
                raise ToolFault("scope_repo_conflict")
    # Validate and sanitize all inputs BEFORE the first write.
    _string(args, "parent_checkpoint", False)
    _guard_data(args)
    s = copy.deepcopy(snap)
    s["_handoffstone_repo"] = repo
    _guard_data(s)
    new_ids = []
    try:
        for d in decisions:
            record = hs.capture_decision(
                project_scope=scope, agent=agent, title=d["title"],
                decision=d["decision"], rationale=d["rationale"],
                evidence_refs=evidence,
                status=hs.VerificationStatus(d.get("status", "agent_inferred")),
                supersedes=d.get("supersedes", []))
            new_ids.append(record.id)
        rec = hs.create_checkpoint(
            project_scope=scope, agent=agent, label=label,
            snapshot=s, parent_checkpoint=args.get("parent_checkpoint", ""),
            evidence_refs=evidence)
    except Exception as exc:
        raise ToolFault("write_failed_partial_write_possible") from exc
    return {"written": True, "scope": scope, "checkpoint_id": rec.id,
            "decision_ids": new_ids, "evidence_verified": sum(e.verified for e in evidence)}


def _resume(args: dict) -> dict:
    _guard_data(args)
    result, _ = _assemble(args)
    _guard_data(result)  # Do not leak legacy or externally inserted secrets.
    return result


def _handoff(args: dict) -> dict:
    _guard_data(args)
    source, target = _string(args, "source_agent"), _string(args, "target_agent")
    task_summary = _string(args, "task_summary")
    result, package = _assemble(args)
    if not result["ready"]:
        raise ToolFault("handoff_blocked_" + result["state"])
    _guard_data(result)  # Check outgoing memory before persisting a handoff.
    try:
        record = hs.create_handoff(
            project_scope=result["scope"], source_agent=source,
            target_agent=target, task_summary=task_summary, package=package)
    except Exception as exc:
        raise ToolFault("handoff_write_failed") from exc
    return {"written": True, "handoff_id": record.id,
            "scope": result["scope"], "checkpoint_id": result["checkpoint_id"]}


TOOLS = [
    {"name": "context_checkpoint", "description": "Store a Git-bound project checkpoint and optional decisions (writes).",
     "inputSchema": {"type": "object", "properties": {
         "project_scope": {"type": "string"}, "repo_path": {"type": "string"},
         "agent": {"type": "string"}, "label": {"type": "string"},
         "snapshot": {"type": "object"}, "evidence": {"type": "array"},
         "decisions": {"type": "array"}, "parent_checkpoint": {"type": "string"}},
         "required": ["project_scope", "repo_path", "agent", "label", "snapshot"],
         "additionalProperties": False}},
    {"name": "context_resume", "description": "Read matching Git-bound project context (read-only).",
     "inputSchema": {"type": "object", "properties": {
         "project_scope": {"type": "string"}, "repo_path": {"type": "string"},
         "max_tokens": {"type": "integer", "minimum": 500, "maximum": 30000}},
         "required": ["project_scope", "repo_path"], "additionalProperties": False}},
    {"name": "context_handoff", "description": "Persist a validated context package for a target agent (writes).",
     "inputSchema": {"type": "object", "properties": {
         "project_scope": {"type": "string"}, "repo_path": {"type": "string"},
         "source_agent": {"type": "string"}, "target_agent": {"type": "string"},
         "task_summary": {"type": "string"},
         "max_tokens": {"type": "integer", "minimum": 500, "maximum": 30000}},
         "required": ["project_scope", "repo_path", "source_agent", "target_agent", "task_summary"],
         "additionalProperties": False}},
]


def _reply(req: dict) -> dict | None:
    method = req.get("method")
    msg_id = req.get("id")
    if method is None:
        raise ToolFault("invalid_request")
    if msg_id is None:  # Notifications have no responses.
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "handoffstone-m4", "version": "0.1.0-prototype"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32601, "message": "Method not found"}}
    params = req.get("params", {})
    if not isinstance(params, dict) or not isinstance(params.get("arguments", {}), dict):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32602, "message": "Invalid params"}}
    name, args = params.get("name"), params.get("arguments", {})
    implementations = {"context_checkpoint": _checkpoint,
                       "context_resume": _resume, "context_handoff": _handoff}
    try:
        if name not in implementations:
            raise ToolFault("unknown_tool")
        _required_core()
        result = implementations[name](args)
        _guard_data(result)
        out = {"result": result}
        failed = False
    except ToolFault as exc:
        out = {"error": {"code": exc.code}}
        failed = True
    except Exception as exc:
        # Stable error taxonomy; never print user text, credentials or tracebacks.
        mapping = {"StoreCorruptionError": "store_corrupt",
                   "StoreUnavailableError": "store_unavailable",
                   "StoreWriteError": "store_write_failed",
                   "UnsafeContentError": "unsafe_content_rejected",
                   "InvalidScopeError": "invalid_project_scope",
                   "VerificationError": "verification_failed"}
        out = {"error": {"code": mapping.get(type(exc).__name__, "internal_error")}}
        failed = True
    return {"jsonrpc": "2.0", "id": msg_id, "result": {
        "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
        "isError": failed}}


def main() -> None:
    # stdout is exclusively for JSON-RPC messages, never debug prints.
    for raw in sys.stdin.buffer:
        if len(raw) > MAX_LINE:
            continue  # refuse oversized requests without echoing contents
        try:
            req = json.loads(raw)
            if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
                reply = {"jsonrpc": "2.0", "id": None, "error": {
                    "code": -32600, "message": "Invalid Request"}}
            else:
                reply = _reply(req)
        except (UnicodeDecodeError, json.JSONDecodeError):
            reply = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": "Parse error"}}
        except ToolFault:
            reply = {"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None,
                     "error": {"code": -32600, "message": "Invalid Request"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
