"""Public-boundary P0 acceptance tests. Stdlib only; synthetic isolated stores."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import handoffstone as h


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="handoffstone_p0_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old_store = h.HANDOFFSTONE_DIR
        h.HANDOFFSTONE_DIR = self.root / "store"
        self.addCleanup(setattr, h, "HANDOFFSTONE_DIR", self.old_store)
        self.fake_secret = "sk-" + "SYNTHETIC_ONLY_0123456789" * 2

    def record(self, kind=h.RecordKind.DECISION_RECORD, **kwargs):
        return h.create_record(kind, project_scope="project-A", created_by="test", **kwargs)

    def evidence(self):
        return h.EvidenceReference(id="test-attestation", kind="test", locator=__file__, verified=True)

    def raw_store(self, content):
        path = h.get_context_store_path("project-A")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def test_all_record_types_reject_unbacked_verified(self):
        for kind in h.RecordKind:
            if kind == h.RecordKind.EVIDENCE_REFERENCE:
                continue
            with self.subTest(kind=kind), self.assertRaises(h.VerificationError):
                self.record(kind, status=h.VerificationStatus.VERIFIED)

    def test_verified_requires_attested_usable_reference(self):
        for ev in (h.EvidenceReference(id="e", kind="file", locator="source.py"),
                   h.EvidenceReference(id="e", kind="file", locator="")):
            with self.subTest(ev=ev), self.assertRaises(h.VerificationError):
                self.record(status=h.VerificationStatus.VERIFIED, evidence=[ev])
        for locator in ("", " ", "[REDACTED]"):
            with self.subTest(locator=locator), self.assertRaises(h.VerificationError):
                h.EvidenceReference(id="e", kind="test", locator=locator, verified=True)

    def test_attested_verified_roundtrip_and_storage(self):
        r = self.record(status=h.VerificationStatus.VERIFIED, evidence=[self.evidence()])
        self.assertIs(h.save_record(r), True)
        loaded = h.load_records("project-A")[0]
        self.assertEqual(loaded.to_dict(), r.to_dict())
        self.assertEqual(loaded.status, h.VerificationStatus.VERIFIED)

    def test_mutation_cannot_bypass_verified_validation(self):
        r = self.record()
        r.status = h.VerificationStatus.VERIFIED
        for action in (r.to_dict, r.to_json, lambda: h.record_to_json(r), lambda: h.save_record(r)):
            with self.subTest(action=action), self.assertRaises(h.VerificationError):
                action()
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_mutated_evidence_is_rechecked(self):
        r = self.record(status=h.VerificationStatus.VERIFIED, evidence=[self.evidence()])
        r.evidence[0].locator = ""
        with self.assertRaises(h.VerificationError):
            h.save_record(r)

    def test_invalid_mutated_status_and_kind_cannot_poison_store(self):
        for field, value in (("status", "made-up"), ("kind", "unknown")):
            r = self.record()
            setattr(r, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                h.save_record(r)
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_legacy_unbacked_verified_import_is_rejected(self):
        data = self.record().to_dict()
        data["status"] = "verified"
        with self.assertRaises(h.VerificationError):
            h.record_from_json(json.dumps(data))
        with self.assertRaises(h.VerificationError):
            h.ContextPackage.from_json(json.dumps({"decisions": [data]}))

    def test_wire_unbacked_verified_import_is_rejected(self):
        data = h.ContextPackage(decisions=[self.record()]).to_wire_dict()
        data["d"][0]["st"] = "verified"
        with self.assertRaises(h.VerificationError):
            h.ContextPackage.from_wire_dict(data)

    def test_wire_false_string_cannot_attest_evidence(self):
        r = self.record(status=h.VerificationStatus.VERIFIED, evidence=[self.evidence()])
        data = h.ContextPackage(decisions=[r]).to_wire_dict()
        data["d"][0]["ev"][0]["v"] = "false"
        with self.assertRaises(h.VerificationError):
            h.ContextPackage.from_wire_dict(data)

    def test_raw_verified_nested_record_is_rejected(self):
        data = self.record().to_dict()
        data["status"] = "verified"
        with self.assertRaises(h.VerificationError):
            h.create_checkpoint("project-A", "test", "bad", {"decisions": [data]})

    def test_capture_helpers_propagate_write_failure(self):
        path = h.get_context_store_path("project-A")
        path.mkdir(parents=True)
        calls = [
            lambda: h.save_record(self.record()),
            lambda: h.capture_decision("project-A", "test", "d", "use x", "r"),
            lambda: h.capture_constraint("project-A", "test", "local only"),
            lambda: h.capture_working_state("project-A", "test", "fix bug"),
            lambda: h.create_checkpoint("project-A", "test", "cp", {}),
            lambda: h.create_handoff("project-A", "test", "other", "task", h.ContextPackage()),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(h.StoreWriteError):
                call()

    def test_store_directory_failure_is_visible(self):
        h.HANDOFFSTONE_DIR.write_text("not a directory")
        with self.assertRaises(h.StoreWriteError):
            h.save_record(self.record())

    def test_sync_failure_is_not_a_successful_checkpoint(self):
        with patch.object(h.os, "fsync", side_effect=OSError("synthetic sync failure")):
            with self.assertRaises(h.StoreWriteError):
                h.create_checkpoint("project-A", "test", "cp", {"next": "verify"})
        # Bytes may already exist: failure is unconfirmed persistence, not rollback.
        self.assertEqual(len(h.load_records("project-A")), 1)

    def test_checkpoint_is_readable_in_a_fresh_process(self):
        cp = h.create_checkpoint("project-A", "test", "cp", {"next": "run acceptance"})
        env = os.environ.copy()
        env.update(HANDOFFSTONE_HOME=str(h.HANDOFFSTONE_DIR), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import handoffstone as h; print(h.get_latest_record('project-A', h.RecordKind.CONTEXT_CHECKPOINT).to_json())"],
            cwd=Path(h.__file__).parent, env=env, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout)["id"], cp.id)
        self.assertEqual(json.loads(result.stdout)["snapshot"], cp.snapshot)

    def test_missing_and_valid_empty_store_are_empty(self):
        self.assertEqual(h.load_records("project-A"), [])
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())
        self.raw_store("\n  \n")
        self.assertEqual(h.load_records("project-A"), [])

    def test_corrupt_line_never_becomes_empty_or_partial(self):
        good = h.record_to_json(self.record())
        for content, line in (("{broken", 1), (good + "\n{broken\n", 2)):
            with self.subTest(line=line):
                path = self.raw_store(content)
                before = path.read_bytes()
                with self.assertRaises(h.StoreCorruptionError) as caught:
                    h.load_records("project-A")
                self.assertEqual(caught.exception.line_number, line)
                self.assertEqual(path.read_bytes(), before)

    def test_filter_does_not_hide_corruption(self):
        self.raw_store('{"kind":"WorkingState","broken":true}\n')
        with self.assertRaises(h.StoreCorruptionError):
            h.load_records("project-A", h.RecordKind.DECISION_RECORD)

    def test_wrong_json_shapes_and_encoding_are_corruption(self):
        for raw in (b"[]\n", b"null\n", b"42\n", b"{}\n", b"\xff\n"):
            with self.subTest(raw=raw):
                self.raw_store(raw)
                with self.assertRaises(h.StoreCorruptionError):
                    h.get_latest_record("project-A", h.RecordKind.CONTEXT_CHECKPOINT)

    def test_unavailable_store_is_not_empty(self):
        h.HANDOFFSTONE_DIR.write_text("not a directory")
        with self.assertRaises(h.StoreUnavailableError):
            h.load_records("project-A")

    def test_read_failure_after_a_good_line_is_not_partial_success(self):
        self.raw_store(h.record_to_json(self.record()) + "\n")
        original_fdopen = h.os.fdopen

        class InterruptedReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def __iter__(self):
                yield self.stream.readline()
                raise OSError("synthetic mid-stream read failure")

        def interrupted(fd, *args, **kwargs):
            return InterruptedReader(original_fdopen(fd, *args, **kwargs))

        with patch.object(h.os, "fdopen", side_effect=interrupted):
            with self.assertRaises(h.StoreUnavailableError):
                h.load_records("project-A")

    def test_invalid_scope_rejected_before_filesystem_access(self):
        for scope in ("", ".", "..", "../escape", "a/../../b", "/tmp/escape", "a\\b", "a\x00b", "a\nb", "a:b", "a b", "x" * 129, None, 42):
            for call in (h.get_context_store_path, h.load_records):
                if scope == "" and call is h.load_records:
                    # Preserve the already-published no-scope behavior while
                    # ensuring it cannot enumerate or touch the store.
                    with self.subTest(scope=scope, call=call):
                        self.assertEqual(call(scope), [])
                    continue
                with self.subTest(scope=scope, call=call), self.assertRaises(h.InvalidScopeError):
                    call(scope)
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_valid_scope_filenames_preserved(self):
        for scope in ("project-A", "repo.name_1", "123", "x" * 128):
            self.assertEqual(h.get_context_store_path(scope), h.HANDOFFSTONE_DIR / (scope + ".jsonl"))

    def test_scope_override_cannot_relabel_record(self):
        for scope in ("project-B", "", "../outside"):
            with self.subTest(scope=scope), self.assertRaises(h.InvalidScopeError):
                h.save_record(self.record(), scope=scope)
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_foreign_record_in_store_is_corruption(self):
        r = h.create_record(h.RecordKind.DECISION_RECORD, "project-B", "test")
        self.raw_store(h.record_to_json(r) + "\n")
        with self.assertRaises(h.StoreCorruptionError):
            h.load_records("project-A")

    def test_symlink_store_is_never_followed(self):
        target = self.root / "outside.jsonl"
        target.write_text("outside remains intact")
        path = h.get_context_store_path("project-A")
        path.parent.mkdir()
        path.symlink_to(target)
        with self.assertRaises(h.StoreWriteError):
            h.save_record(self.record())
        with self.assertRaises(h.StoreUnavailableError):
            h.load_records("project-A")
        self.assertEqual(target.read_text(), "outside remains intact")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO check")
    def test_special_store_cannot_hang_or_return_empty(self):
        path = h.get_context_store_path("project-A")
        path.parent.mkdir()
        os.mkfifo(path)
        with self.assertRaises(h.StoreUnavailableError):
            h.load_records("project-A")
        with self.assertRaises(h.StoreWriteError):
            h.save_record(self.record())

    def test_all_record_types_reject_nested_sensitive_content(self):
        for kind in h.RecordKind:
            if kind == h.RecordKind.EVIDENCE_REFERENCE:
                continue
            with self.subTest(kind=kind), self.assertRaises(h.UnsafeContentError):
                self.record(kind, metadata={"nested": [{"value": self.fake_secret}]})
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_mutated_record_export_and_save_are_protected(self):
        r = self.record()
        r.metadata["nested"] = {"value": self.fake_secret}
        for action in (r.to_dict, r.to_json, lambda: h.record_to_json(r), lambda: h.save_record(r)):
            with self.subTest(action=action), self.assertRaises(h.UnsafeContentError) as caught:
                action()
            self.assertNotIn(self.fake_secret, str(caught.exception))
        self.assertFalse(h.HANDOFFSTONE_DIR.exists())

    def test_checkpoint_and_raw_handoff_nested_secrets_rejected(self):
        with self.assertRaises(h.UnsafeContentError):
            h.create_checkpoint("project-A", "test", "cp", {"nested": [{"value": self.fake_secret}]})
        with self.assertRaises(h.UnsafeContentError):
            self.record(h.RecordKind.HANDOFF_RECORD, package={"nested": self.fake_secret})

    def test_sensitive_keys_are_checked_even_for_short_values(self):
        for key in ("password", "api_key", "accessToken", "Authorization", "private_key"):
            with self.subTest(key=key), self.assertRaises(h.UnsafeContentError):
                self.record(metadata={key: "short"})
        self.record(metadata={"api_key": "[REDACTED]", "secret_path": "vault/local-service"})

    def test_package_exports_recheck_mutable_nested_fields(self):
        pkg = h.ContextPackage(decisions=[self.record()])
        pkg.open_questions.append(self.fake_secret)
        for action in (pkg.to_dict, pkg.to_json, pkg.to_markdown, pkg.to_wire_dict, pkg.to_wire_json):
            with self.subTest(action=action), self.assertRaises(h.UnsafeContentError):
                action()

    def test_import_boundaries_reject_sensitive_fields(self):
        pkg = h.ContextPackage(decisions=[self.record()])
        legacy = pkg.to_dict()
        legacy["uncertainty"] = [self.fake_secret]
        wire = pkg.to_wire_dict()
        wire["un"] = [self.fake_secret]
        for action in (lambda: h.ContextPackage.from_json(json.dumps(legacy)),
                       lambda: h.ContextPackage.from_wire_dict(legacy),
                       lambda: h.ContextPackage.from_wire_json(json.dumps(wire))):
            with self.subTest(action=action), self.assertRaises(h.UnsafeContentError):
                action()

    def test_mutated_package_evidence_is_rechecked(self):
        ev = self.evidence()
        pkg = h.ContextPackage(evidence=[ev])
        ev.verified = "false"
        with self.assertRaises(h.VerificationError):
            pkg.to_wire_json()

    def test_unsafe_legacy_store_reports_corruption_without_echo(self):
        data = self.record().to_dict()
        data["metadata"] = {"value": self.fake_secret}
        self.raw_store(json.dumps(data) + "\n")
        with self.assertRaises(h.StoreCorruptionError) as caught:
            h.load_records("project-A")
        self.assertNotIn(self.fake_secret, str(caught.exception))

    def test_unknown_import_fields_do_not_hide_secrets_in_legacy_store(self):
        data = self.record().to_dict()
        data["unknown_field"] = self.fake_secret
        self.raw_store(json.dumps(data) + "\n")
        with self.assertRaises(h.StoreCorruptionError):
            h.load_records("project-A")

    def test_explicit_redaction_is_accepted_and_idempotent(self):
        for text in (self.fake_secret, 'password="short"', "Authorization: Bearer abc.def.ghi", "contact user@example.com",
                     "AKIA" + "A" * 16, "-----BEGIN PRIVATE KEY-----\nSYNTHETIC\n-----END PRIVATE KEY-----"):
            with self.subTest(text=text):
                safe = h.sanitize_for_transfer(text)
                self.assertEqual(h.sanitize_for_transfer(safe), safe)
                self.assertEqual(h.detect_secrets(safe), [])
                h.capture_working_state("project-A", "test", safe)

    def test_manual_and_consumer_import_paths_cannot_bypass_boundary(self):
        with self.assertRaises(h.UnsafeContentError):
            h.create_manual_handoff_input("project-A", decisions=[{"decision": self.fake_secret}])
        conversation = {"id": "fixture", "messages": [{"role": "user", "content": "Decision: we will use SQLite because " + self.fake_secret}]}
        records = h.extract_decisions_from_conversation(conversation, "project-A", "test")
        self.assertEqual(len(records), 1)
        self.assertNotIn(self.fake_secret, h.record_to_json(records[0]))

    def test_valid_legacy_full_and_wire_shapes_are_preserved(self):
        r = self.record(title="Use local storage", decision="JSONL", rationale="No service required")
        pkg = h.ContextPackage(decisions=[r], uncertainty=["Recheck live state"])
        data = pkg.to_dict()
        full = json.dumps(data)
        self.assertEqual(h.ContextPackage.from_json(full).to_dict(), data)
        self.assertEqual(h.ContextPackage.from_wire_json(full).to_dict(), data)
        self.assertEqual(h.ContextPackage.from_wire_json(pkg.to_wire_json()).to_dict(), data)
        self.assertEqual(h.record_from_json(h.record_to_json(r)).to_dict(), r.to_dict())

    def _pre_p0_module(self):
        """Import the untouched pre-P0 module from git HEAD (read-only)."""
        repo = Path(h.__file__).parent
        try:
            out = subprocess.run(["git", "show", "HEAD:handoffstone.py"], cwd=repo,
                                 capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise unittest.SkipTest(f"pre-P0 module unavailable: {exc}") from None
        target = self.root / "legacy_handoffstone.py"
        target.write_text(out.stdout, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("legacy_handoffstone_pre_p0", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_pre_p0_fixtures_are_consumed_by_new_apis(self):
        legacy = self._pre_p0_module()
        legacy.HANDOFFSTONE_DIR = h.HANDOFFSTONE_DIR
        ev = legacy.EvidenceReference(id="legacy-attestation", kind="test",
                                      locator="results/old.json", verified=True)
        decision = legacy.create_record(
            legacy.RecordKind.DECISION_RECORD, project_scope="project-A", created_by="legacy",
            title="Use local storage", decision="Keep JSONL", rationale="No service needed",
            evidence=[ev], status=legacy.VerificationStatus.VERIFIED,
        )
        checkpoint = legacy.create_checkpoint("project-A", "legacy", "cp", {"next": "verify"})
        self.assertTrue(legacy.save_record(decision))
        pkg = legacy.ContextPackage(decisions=[decision], uncertainty=["Recheck live state"])

        loaded = {r.id: r for r in h.load_records("project-A")}
        self.assertEqual(set(loaded), {decision.id, checkpoint.id})
        self.assertEqual(loaded[decision.id].to_dict(), decision.to_dict())
        self.assertEqual(loaded[decision.id].status, h.VerificationStatus.VERIFIED)
        self.assertEqual(loaded[checkpoint.id].snapshot, {"next": "verify"})
        self.assertEqual(h.get_latest_record("project-A", h.RecordKind.CONTEXT_CHECKPOINT).id,
                         checkpoint.id)
        self.assertEqual(h.ContextPackage.from_json(pkg.to_json()).to_dict(), pkg.to_dict())
        self.assertEqual(h.ContextPackage.from_wire_json(pkg.to_json()).to_dict(), pkg.to_dict())
        decoded = h.ContextPackage.from_wire_json(pkg.to_wire_json())
        self.assertEqual(decoded.decisions[0].to_dict(), decision.to_dict())
        self.assertEqual(decoded.uncertainty, pkg.uncertainty)


if __name__ == "__main__":
    unittest.main()
