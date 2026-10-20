#!/usr/bin/env python3
"""Isolated subprocess contract tests. Uses a P0-shaped fake core, NOT local P0.

Run on the user's P0 branch alongside test_reliability.py before declaring M4 PASS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).parent

# Tiny P0-shaped core fixture: exercises MCP dispatch and JSONL across distinct
# processes, not Handoffstone's real persistence/validation implementation.
FAKE_CORE = r'''
import os,json,datetime,uuid
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
class HandoffstoneError(Exception): pass
class StoreWriteError(HandoffstoneError): pass
class StoreCorruptionError(HandoffstoneError): pass
class StoreUnavailableError(HandoffstoneError): pass
class UnsafeContentError(HandoffstoneError): pass
class InvalidScopeError(HandoffstoneError): pass
class VerificationError(HandoffstoneError): pass
class VerificationStatus(str,Enum):
    VERIFIED='verified'; USER_ASSERTED='user_asserted'; AGENT_INFERRED='agent_inferred'; UNVERIFIED='unverified'; SUPERSEDED='superseded'
class RecordKind(str,Enum):
    DECISION_RECORD='DecisionRecord'; CONSTRAINT_RECORD='ConstraintRecord'; CONTEXT_CHECKPOINT='ContextCheckpoint'; HANDOFF_RECORD='HandoffRecord'; WORKING_STATE='WorkingState'
@dataclass
class EvidenceReference:
    id:str; kind:str; locator:str; description:str=''; verified:bool=False
class Record:
    def __init__(self,**kw): self.__dict__.update(kw)
    def to_dict(self): return clean(self.__dict__)
class WorkingState(Record): pass
def clean(x):
    if isinstance(x,Enum): return x.value
    if isinstance(x,list): return [clean(v) for v in x]
    if isinstance(x,dict): return {k:clean(v) for k,v in x.items()}
    if hasattr(x,'__dict__'): return clean(x.__dict__)
    return x
def revive(d):
    d['kind']=RecordKind(d['kind']); d['status']=VerificationStatus(d.get('status','unverified'))
    d['evidence']=[EvidenceReference(**e) for e in d.get('evidence',[])]
    return Record(**d)
HANDOFFSTONE_DIR=Path(os.environ.get('HANDOFFSTONE_HOME',str(Path.home()/'.handoffstone')))
def detect_secrets(t):
    import re
    return re.findall(r'(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})',t)
def save_record(r):
    if os.environ.get('STUB_FAIL_WRITE'): raise StoreWriteError()
    HANDOFFSTONE_DIR.mkdir(parents=True,exist_ok=True)
    with open(HANDOFFSTONE_DIR/(r.project_scope+'.jsonl'),'a') as f:
        f.write(json.dumps(r.to_dict())+'\n')
def load_records(scope):
    p=HANDOFFSTONE_DIR/(scope+'.jsonl')
    if not p.exists(): return []
    try:
        rows=[revive(json.loads(l)) for l in p.read_text().splitlines() if l]
    except Exception as e: raise StoreCorruptionError() from e
    dedup={}
    for row in rows: dedup[row.id]=row
    return list(dedup.values())
def mk(kind,scope,agent,**kw):
    return Record(id=uuid.uuid4().hex,kind=kind,project_scope=scope,created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),created_by=agent,
        status=kw.pop('status',VerificationStatus.UNVERIFIED), evidence=kw.pop('evidence',[]),**kw)
def capture_decision(project_scope,agent,title,decision,rationale,evidence_refs=None,status=VerificationStatus.AGENT_INFERRED,supersedes=None):
    r=mk(RecordKind.DECISION_RECORD,project_scope,agent,title=title,decision=decision,rationale=rationale,status=status,evidence=evidence_refs or [],supersedes=supersedes or [],superseded_by=[])
    save_record(r)
    if supersedes:
        for old in load_records(project_scope):
            if old.id in supersedes:
                old.status=VerificationStatus.SUPERSEDED
                old.superseded_by.append(r.id)
                save_record(old)
    return r
def create_checkpoint(project_scope,agent,label,snapshot,parent_checkpoint='',evidence_refs=None):
    r=mk(RecordKind.CONTEXT_CHECKPOINT,project_scope,agent,label=label,snapshot=snapshot,parent_checkpoint=parent_checkpoint,evidence=evidence_refs or [])
    save_record(r); return r
def create_handoff(project_scope,source_agent,target_agent,task_summary,package,evidence_refs=None):
    r=mk(RecordKind.HANDOFF_RECORD,project_scope,source_agent,source_agent=source_agent,target_agent=target_agent,task_summary=task_summary,package=package.to_dict())
    save_record(r); return r
def get_context_store_path(scope):
    return HANDOFFSTONE_DIR/(scope+'.jsonl')
def record_to_json(r):
    return json.dumps(r.to_dict(),separators=(',',':'))
def create_record(kind,project_scope,created_by,**kw):
    kw.setdefault('superseded_by',[])
    return mk(kind,project_scope,created_by,**kw)
def build_supersession_history(decisions):
    return [{'supersedes':old.id,'successor':new.id} for old in decisions for new in decisions if old.id in getattr(new,'supersedes',[])]
class ContextPackage:
    def __init__(self,decisions=None,constraints=None,supersession_history=None,working_state=None,created_by=''):
        self.decisions=decisions or []; self.constraints=constraints or []; self.supersession_history=supersession_history or []; self.working_state=working_state;self.created_by=created_by
    def to_dict(self): return clean(self.__dict__)
    def to_wire_json(self): return json.dumps(self.to_dict(),ensure_ascii=False,separators=(',',':'))
def fit_package_to_budget(package,max_tokens,wire='compact'):
    # Contract tests do not validate budget algorithms; the real core does.
    return package
'''


class BridgeContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m4_fake_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bridge = self.root / "mcp_stdio.py"
        shutil.copy(HERE / "mcp_stdio.py", self.bridge)
        (self.root / "handoffstone.py").write_text(FAKE_CORE)
        self.store = self.root / "store"
        self.workspace = self.root / "workspaces"
        self.workspace.mkdir()
        self.repo = self.git_repo("p1")
        self.env = dict(os.environ, HOME=str(self.root / "home"),
                        HANDOFFSTONE_HOME=str(self.store),
                        HANDOFFSTONE_ALLOWED_REPO_ROOT=str(self.workspace))

    def git_repo(self, name):
        root = self.workspace / name
        root.mkdir()
        for cmd in (["init", "-q"], ["config", "user.name", "M4 Test"],
                    ["config", "user.email", "fake@example.invalid"]):
            subprocess.run(["git", "-C", str(root)] + cmd, check=True,
                           capture_output=True)
        (root / "README.md").write_text("Initial repository\n")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True, capture_output=True)
        return root

    def call(self, name, args=None, env=None):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion":"2025-06-18", "capabilities":{}, "clientInfo":{"name":"fake","version":"1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": name, "arguments": args or {}}}
        ]
        res = subprocess.run([sys.executable, str(self.bridge)],
                             input="\n".join(json.dumps(m) for m in messages)+"\n",
                             capture_output=True, text=True,
                             env=env or self.env, timeout=10)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = [json.loads(l) for l in res.stdout.splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "handoffstone-m4")
        reply = lines[1]["result"]
        payload = json.loads(reply["content"][0]["text"])
        return reply["isError"], payload.get("result") or payload.get("error")

    def checkpoint(self, **kw):
        args={"project_scope":"p1", "repo_path":str(self.repo),
              "agent":"fake", "label":"halted",
              "snapshot":{"active_task":"repair parser", "next_action":"run fixture tests", "state":"in_progress"}}
        args.update(kw)
        return self.call("context_checkpoint",args)

    def resume(self, **kw):
        args={"project_scope":"p1", "repo_path":str(self.repo)}
        args.update(kw)
        return self.call("context_resume",args)

    def test_session_a_b_separate_processes(self):
        error, saved=self.checkpoint(decisions=[{"title":"Persistence","decision":"Use JSONL", "rationale":"No daemon"}],
                                     evidence=[{"kind":"file","locator":"README.md"}])
        self.assertFalse(error)
        self.assertTrue(saved["written"])
        error, resumed=self.resume()  # distinct subprocess
        self.assertFalse(error)
        self.assertTrue(resumed["ready"])
        self.assertEqual(resumed["context"]["decisions"][0]["decision"],"Use JSONL")
        self.assertEqual(resumed["snapshot"]["next_action"],"run fixture tests")
        self.assertEqual(resumed["context"]["decisions"][0]["evidence"][0]["verified"], True)

    def test_empty_is_not_corrupt(self):
        self.assertEqual(self.resume()[1]["state"],"empty")
        self.store.mkdir(exist_ok=True)
        (self.store / "p1.jsonl").write_text("{bad json\n")
        err,result=self.resume()
        self.assertTrue(err)
        self.assertEqual(result["code"],"store_corrupt")

    def test_scope_escape_rejected(self):
        err,result=self.checkpoint(project_scope="../victim")
        self.assertTrue(err)
        self.assertEqual(result["code"],"invalid_project_scope")

    def test_secret_rejection_nested(self):
        err,result=self.checkpoint(snapshot={"active_task":"A", "next_action":"B",
                                                   "progress":{"secret":"sk-abcdefghijklmnopqrstuvwxyz012345"}})
        self.assertTrue(err)
        self.assertEqual(result["code"],"unsafe_content_rejected")
        self.assertFalse(self.store.exists())

    def test_stale_head(self):
        self.assertFalse(self.checkpoint()[0])
        (self.repo/"README.md").write_text("changed")
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qam", "next"],check=True,capture_output=True)
        err,result=self.resume()
        self.assertFalse(err)
        self.assertEqual(result["state"],"stale_head")
        self.assertIsNone(result["context"])

    def test_stale_branch(self):
        self.assertFalse(self.checkpoint()[0])
        subprocess.run(["git", "-C",str(self.repo), "checkout", "-qb", "other"],check=True,capture_output=True)
        self.assertEqual(self.resume()[1]["state"], "stale_branch")

    def test_different_repo_same_scope_blocked(self):
        self.assertFalse(self.checkpoint()[0])
        other=self.git_repo("other")
        self.assertEqual(self.resume(repo_path=str(other))[1]["state"],"project_mismatch")

    def test_other_scope_does_not_receive_records(self):
        self.assertFalse(self.checkpoint()[0])
        self.assertEqual(self.resume(project_scope="p2")[1]["state"],"empty")

    def test_superseded_record_excluded(self):
        old=self.checkpoint(decisions=[{"title":"Database", "decision":"SQLite", "rationale":"Simple"}])[1]["decision_ids"][0]
        self.assertFalse(self.checkpoint(decisions=[{"title":"Database", "decision":"Postgres", "rationale":"Concurrency", "supersedes":[old]}])[0])
        r=self.resume()[1]
        self.assertEqual([d["decision"] for d in r["context"]["decisions"]],["Postgres"])
        self.assertEqual(len(r["context"]["supersession_history"]),1)

    def test_missing_evidence_downgrades(self):
        # A legacy 'verified' record can only be downgraded while the repo
        # digest is unchanged, so the doomed locator must live OUTSIDE the git
        # tree (e.g. inside the store folder).
        marker = self.store / "external_marker.md"
        self.store.mkdir(exist_ok=True)
        marker.write_text("legacy evidence\n")
        err, saved = self.checkpoint(decisions=[{"title": "Verified", "decision": "Use X", "rationale": "Code"}],
                                     evidence=[{"kind": "file", "locator": str(marker)}])
        self.assertFalse(err)
        rows = (self.store / "p1.jsonl").read_text().splitlines()
        lines = []
        for row in rows:
            obj = json.loads(row)
            if obj.get("kind") == "DecisionRecord":
                obj["status"] = "verified"
                obj["evidence"] = [{"id": "e0", "kind": "file", "locator": str(marker),
                                    "description": "", "verified": True}]
            lines.append(json.dumps(obj))
        (self.store / "p1.jsonl").write_text("\n".join(lines) + "\n")
        marker.unlink()
        err, result = self.resume()
        self.assertFalse(err)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["context"]["decisions"][0]["status"], "unverified")

    def test_no_verified_without_evidence(self):
        err,result=self.checkpoint(decisions=[{"title":"Claim", "decision":"Done", "rationale":"Said", "status":"verified"}])
        self.assertTrue(err)
        self.assertEqual(result["code"],"independent_verification_required")

    def test_verified_not_promoted_by_existing_file(self):
        err, result = self.checkpoint(decisions=[{"title":"False confidence", "decision":"Use X", "rationale":"File exists", "status":"verified"}],
                                      evidence=[{"kind":"file", "locator":"README.md"}])
        self.assertTrue(err)
        self.assertEqual(result["code"], "independent_verification_required")

    def test_scope_cannot_rebind_to_other_repo(self):
        self.assertFalse(self.checkpoint()[0])
        other=self.git_repo("other")
        err, result=self.checkpoint(repo_path=str(other))
        self.assertTrue(err)
        self.assertEqual(result["code"],"scope_repo_conflict")

    def test_legacy_secret_is_not_exposed_on_resume(self):
        self.assertFalse(self.checkpoint()[0])
        p=self.store / "p1.jsonl"
        rows=p.read_text().splitlines()
        data=json.loads(rows[0])
        data["snapshot"]["active_task"]="sk-abcdefghijklmnopqrstuvwxyz012345"
        p.write_text(json.dumps(data)+"\n")
        err,result=self.resume()
        self.assertTrue(err)
        self.assertEqual(result["code"],"unsafe_content_rejected")

    def test_write_failure_visible_and_atomic(self):
        # Atomic batch writer: a mid-transaction failure must leave the store
        # byte-identical (no partial multi-record state).
        env = dict(self.env, MCP_FAIL_ATOMIC="1")
        err, result = self.call("context_checkpoint", {"project_scope": "p1", "repo_path": str(self.repo),
                       "agent": "fake", "label": "fail",
                       "snapshot": {"active_task": "repair", "next_action": "retry"}}, env=env)
        self.assertTrue(err)
        self.assertEqual(result["code"], "write_failed_atomic_no_partial")
        self.assertFalse((self.store / "p1.jsonl").exists())

    def test_store_bytes_identical_after_failed_batch(self):
        self.assertFalse(self.checkpoint()[0])
        before = (self.store / "p1.jsonl").read_bytes()
        env = dict(self.env, MCP_FAIL_ATOMIC="1")
        err, _ = self.call("context_checkpoint", {"project_scope": "p1", "repo_path": str(self.repo),
                          "agent": "fake", "label": "fail",
                          "snapshot": {"active_task": "repair", "next_action": "retry"},
                          "decisions": [{"title": "X", "decision": "Y", "rationale": "Z"}]}, env=env)
        self.assertTrue(err)
        self.assertEqual((self.store / "p1.jsonl").read_bytes(), before)

    def test_handoff_persists(self):
        self.assertFalse(self.checkpoint()[0])
        err,result=self.call("context_handoff",{"project_scope":"p1", "repo_path":str(self.repo),
                            "source_agent":"codex", "target_agent":"claude", "task_summary":"continue"})
        self.assertFalse(err)
        self.assertTrue(result["written"])

    def test_handoff_blocks_wrong_branch(self):
        self.assertFalse(self.checkpoint()[0])
        subprocess.run(["git","-C",str(self.repo),"checkout","-qb","other"],check=True,capture_output=True)
        err,result=self.call("context_handoff",{"project_scope":"p1", "repo_path":str(self.repo),
                              "source_agent":"codex", "target_agent":"claude", "task_summary":"continue"})
        self.assertTrue(err)
        self.assertEqual(result["code"],"handoff_blocked_stale_branch")

    def test_old_core_rejected(self):
        text=(self.root/"handoffstone.py").read_text()
        text=text.replace('class StoreWriteError(HandoffstoneError): pass', 'class NoStoreWriteError(HandoffstoneError): pass')
        (self.root/"handoffstone.py").write_text(text)
        err,result=self.resume()
        self.assertTrue(err)
        self.assertEqual(result["code"],"p0_reliability_core_required")

    def test_store_root_required(self):
        env=dict(self.env)
        env.pop("HANDOFFSTONE_HOME")
        err,result=self.call("context_resume",{"project_scope":"p1", "repo_path":str(self.repo)},env=env)
        self.assertTrue(err)
        self.assertEqual(result["code"],"explicit_store_and_allowed_repo_root_required")

    def test_repo_outside_root_rejected(self):
        err,result=self.resume(repo_path=str(self.root))
        self.assertTrue(err)
        self.assertEqual(result["code"],"repo_outside_allowed_root")


    def test_dirty_worktree_blocks_resume_until_identical(self):
        self.assertFalse(self.checkpoint()[0])
        self.assertEqual(self.resume()[1]["state"], "ready")
        scratch = self.repo / "scratch_untracked.txt"
        scratch.write_text("uncommitted scratch\n")
        err, result = self.resume()
        self.assertFalse(err)
        self.assertEqual(result["state"], "worktree_changed")
        self.assertTrue(result.get("dirty"))
        self.assertIsNone(result["context"])
        scratch.unlink()
        self.assertEqual(self.resume()[1]["state"], "ready")

    def test_dirty_digest_persisted_in_checkpoint(self):
        self.assertFalse(self.checkpoint()[0])
        rows = (self.store / "p1.jsonl").read_text().splitlines()
        bound = None
        for row in rows:
            obj = json.loads(row)
            if obj.get("kind") == "ContextCheckpoint":
                bound = obj["snapshot"].get("_handoffstone_repo")
        self.assertIsInstance(bound, dict)
        self.assertTrue(bound.get("dirty_digest"))
        self.assertRegex(bound["dirty_digest"], r"^[a-f0-9]{64}$")

    def test_evidence_locator_outside_repo_is_none_verified(self):
        err, result = self.checkpoint(
            decisions=[{"title": "T", "decision": "D", "rationale": "R"}],
            evidence=[{"kind": "file", "locator": "/etc/hosts"}])
        self.assertFalse(err)
        resumed = self.resume()[1]
        self.assertTrue(resumed["ready"])
        self.assertEqual(resumed["context"]["decisions"][0]["evidence"][0]["verified"], False)


class RealCoreCompat(unittest.TestCase):
    """Runs the bridge against the real Handoffstone core found beside this
    test file at e22c6ff; skipped elsewhere so the fake contract suite stays
    standalone."""

    @classmethod
    def setUpClass(cls):
        if cls._missing_real_core():
            raise unittest.SkipTest("real handoffstone core not beside test")

    @classmethod
    def _missing_real_core(cls):
        body = (HERE / "handoffstone.py").read_text()
        for token in ("StoreCorruptionError", "save_record", "fit_package_to_budget"):
            if token not in body:
                return True
        try:
            subprocess.run([sys.executable, "-c", "import handoffstone"],
                           check=True, capture_output=True, cwd=str(HERE))
        except subprocess.CalledProcessError:
            return True
        return False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="m4_real_")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = root / "store"
        self.workspace = root / "ws"
        self.workspace.mkdir()
        self.repo = self.workspace / "p1"
        self.repo.mkdir()
        for cmd in (["init", "-q"], ["config", "user.email", "m4@example.invalid"],
                    ["config", "user.name", "M4"]):
            subprocess.run(["git", "-C", str(self.repo)] + cmd, check=True, capture_output=True)
        (self.repo / "README.md").write_text("real-core fixture\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "initial"], check=True, capture_output=True)
        self.env = dict(os.environ, HANDOFFSTONE_HOME=str(self.store),
                        HANDOFFSTONE_ALLOWED_REPO_ROOT=str(self.workspace))
        self.bridge = HERE / "mcp_stdio.py"

    def _call(self, name, args, expected_error=None):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": name, "arguments": args}},
        ]
        res = subprocess.run([sys.executable, str(self.bridge)],
                             input="\n".join(json.dumps(m) for m in messages) + "\n",
                             capture_output=True, text=True, env=self.env,
                             cwd=str(HERE), timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = [json.loads(l) for l in res.stdout.splitlines()]
        payload = json.loads(lines[-1]["result"]["content"][0]["text"])
        outer = payload.get("result") or payload.get("error")
        self.assertEqual(lines[-1]["result"]["isError"], expected_error is not None,
                         json.dumps(payload))
        if expected_error:
            self.assertEqual(outer.get("code"), expected_error, str(outer))
        return outer

    def test_real_core_checkpoint_resume_ends_to_end(self):
        saved = self._call("context_checkpoint", {
            "project_scope": "real", "repo_path": str(self.repo), "agent": "real",
            "label": "halted", "snapshot": {"active_task": "probe", "next_action": "verify"},
            "decisions": [{"title": "Real decision", "decision": "Value R", "rationale": "Why R"}],
            "evidence": [{"kind": "file", "locator": "README.md"}]})
        self.assertTrue(saved["written"])
        resumed = self._call("context_resume", {"project_scope": "real", "repo_path": str(self.repo)})
        self.assertEqual(resumed["state"], "ready")
        self.assertEqual(resumed["context"]["decisions"][0]["decision"], "Value R")
        self.assertEqual(resumed["snapshot"]["next_action"], "verify")
        self.assertTrue(resumed["context"]["decisions"][0]["evidence"][0]["verified"])
        self.assertTrue(resumed["repo"]["dirty_digest"])

    def test_real_core_corrupt_store_surfaces(self):
        self._call("context_checkpoint", {
            "project_scope": "real", "repo_path": str(self.repo), "agent": "real",
            "label": "l", "snapshot": {"active_task": "t", "next_action": "n"}})
        self.store.mkdir(exist_ok=True)
        (self.store / "real.jsonl").open("ab").write(b'{"partial":')
        outer = self._call("context_resume", {"project_scope": "real", "repo_path": str(self.repo)},
                           expected_error="store_corrupt")
        self.assertNotIn("state", outer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
