"""Security regression tests for local JSONL stores (stdlib-only)."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

import handoffstone as hs


class StoreSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = hs.HANDOFFSTONE_DIR
        hs.HANDOFFSTONE_DIR = Path(self.tmp.name) / "store"

    def tearDown(self):
        hs.HANDOFFSTONE_DIR = self.old_home
        self.tmp.cleanup()

    def test_valid_scope_still_roundtrips(self):
        record = hs.create_record(
            hs.RecordKind.PROJECT_CONTEXT,
            project_scope="demo-project",
            created_by="tests",
            name="demo",
        )
        self.assertTrue(hs.save_record(record))
        loaded = hs.load_records("demo-project", hs.RecordKind.PROJECT_CONTEXT)
        self.assertEqual([r.id for r in loaded], [record.id])

    def test_empty_scope_load_preserves_isolation(self):
        self.assertEqual(hs.load_records(""), [])

    def test_scopes_cannot_escape_storage_directory(self):
        for invalid_scope in ("", "../outside", "bad/name", "bad\\name", "/tmp/escape"):
            with self.subTest(scope=invalid_scope):
                with self.assertRaises(ValueError):
                    hs.get_context_store_path(invalid_scope)

    def test_symlink_store_is_rejected(self):
        base = Path(self.tmp.name)
        outside = base / "outside.jsonl"
        outside.write_text("unchanged\n", encoding="utf-8")
        (hs.HANDOFFSTONE_DIR).mkdir(parents=True, exist_ok=True)
        try:
            (hs.HANDOFFSTONE_DIR / "linked.jsonl").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink support")
        with self.assertRaises(ValueError):
            hs.get_context_store_path("linked")
        self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged\n")

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions only")
    def test_new_stores_are_private(self):
        record = hs.create_record(
            hs.RecordKind.PROJECT_CONTEXT,
            project_scope="permissions",
            created_by="tests",
        )
        self.assertTrue(hs.save_record(record))
        mode = stat.S_IMODE(hs.get_context_store_path("permissions").stat().st_mode)
        self.assertEqual(mode & 0o077, 0, f"Store should not be group/world-accessible: {oct(mode)}")


if __name__ == "__main__":
    unittest.main()
