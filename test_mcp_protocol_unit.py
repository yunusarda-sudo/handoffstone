"""In-process unit tests for handoffstone_mcp protocol, routing, and boundaries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import handoffstone as hs
import handoffstone_mcp as mcp


class McpProtocolUnitTests(unittest.TestCase):
    def test_scope_validation(self):
        self.assertEqual(mcp._scope("valid-scope_1"), "valid-scope_1")
        self.assertEqual(mcp._scope("Project42"), "Project42")
        with self.assertRaises(mcp.ToolFault) as ctx:
            mcp._scope("invalid scope with spaces")
        self.assertEqual(ctx.exception.code, "invalid_project_scope")
        with self.assertRaises(mcp.ToolFault):
            mcp._scope("-leading-dash")
        with self.assertRaises(mcp.ToolFault):
            mcp._scope("")
        with self.assertRaises(mcp.ToolFault):
            mcp._scope(123)

    def test_reply_ping_and_notifications(self):
        # Ping
        ping_res = mcp._reply({"jsonrpc": "2.0", "id": 10, "method": "ping"})
        self.assertEqual(ping_res, {"jsonrpc": "2.0", "id": 10, "result": {}})

        # Notification (no id) -> None
        notif_res = mcp._reply({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(notif_res)

        # Missing method
        with self.assertRaises(mcp.ToolFault):
            mcp._reply({"jsonrpc": "2.0", "id": 11})

    def test_reply_initialize_and_tools_list(self):
        init_res = mcp._reply({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        })
        self.assertIsNotNone(init_res)
        self.assertEqual(init_res["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "handoffstone-mcp")

        tools_res = mcp._reply({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = tools_res["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        self.assertEqual(tool_names, {"context_checkpoint", "context_resume", "context_handoff"})

    def test_reply_method_not_found_and_invalid_params(self):
        # Unknown method
        err_method = mcp._reply({"jsonrpc": "2.0", "id": 3, "method": "unknown/method"})
        self.assertEqual(err_method["error"]["code"], -32601)

        # Invalid params (arguments not dict)
        err_params = mcp._reply({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": "not-a-dict",
        })
        self.assertEqual(err_params["error"]["code"], -32602)

        err_params2 = mcp._reply({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"arguments": "not-a-dict"},
        })
        self.assertEqual(err_params2["error"]["code"], -32602)

    def test_reply_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            root = Path(tmp) / "repo"
            root.mkdir()
            old_store = os.environ.get("HANDOFFSTONE_HOME")
            old_root = os.environ.get("HANDOFFSTONE_ALLOWED_REPO_ROOT")
            old_hs_dir = hs.HANDOFFSTONE_DIR
            try:
                os.environ["HANDOFFSTONE_HOME"] = str(store)
                os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = str(root)
                hs.HANDOFFSTONE_DIR = store

                res = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "non_existent_tool", "arguments": {}},
                })
                self.assertTrue(res["result"]["isError"])
                parsed = json.loads(res["result"]["content"][0]["text"])
                self.assertEqual(parsed["error"]["code"], "unknown_tool")
            finally:
                hs.HANDOFFSTONE_DIR = old_hs_dir
                if old_store is not None:
                    os.environ["HANDOFFSTONE_HOME"] = old_store
                else:
                    os.environ.pop("HANDOFFSTONE_HOME", None)
                if old_root is not None:
                    os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = old_root
                else:
                    os.environ.pop("HANDOFFSTONE_ALLOWED_REPO_ROOT", None)

    def test_reply_missing_env_configuration(self):
        old_store = os.environ.get("HANDOFFSTONE_HOME")
        old_root = os.environ.get("HANDOFFSTONE_ALLOWED_REPO_ROOT")
        try:
            os.environ.pop("HANDOFFSTONE_HOME", None)
            os.environ.pop("HANDOFFSTONE_ALLOWED_REPO_ROOT", None)

            res = mcp._reply({
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "context_resume", "arguments": {}},
            })
            self.assertTrue(res["result"]["isError"])
            parsed = json.loads(res["result"]["content"][0]["text"])
            self.assertEqual(parsed["error"]["code"], "explicit_store_and_allowed_repo_root_required")
        finally:
            if old_store is not None:
                os.environ["HANDOFFSTONE_HOME"] = old_store
            if old_root is not None:
                os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = old_root

    def test_in_process_tool_lifecycle_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True, capture_output=True)
            (repo / "test.txt").write_text("v1", encoding="utf-8")
            subprocess.run(["git", "add", "test.txt"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

            store = root / "store"
            old_store = os.environ.get("HANDOFFSTONE_HOME")
            old_root = os.environ.get("HANDOFFSTONE_ALLOWED_REPO_ROOT")
            old_hs_dir = hs.HANDOFFSTONE_DIR
            try:
                os.environ["HANDOFFSTONE_HOME"] = str(store)
                os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = str(repo)
                hs.HANDOFFSTONE_DIR = store

                # 1. Checkpoint with reserved field should fail
                res_bad_snap = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "context_checkpoint",
                        "arguments": {
                            "project_scope": "demo",
                            "repo_path": str(repo),
                            "agent": "test-agent",
                            "label": "fail-cp",
                            "snapshot": {"active_task": "t", "next_action": "n", "_handoffstone_repo": "tamper"},
                        },
                    },
                })
                self.assertTrue(res_bad_snap["result"]["isError"])
                self.assertIn("reserved_snapshot_field", res_bad_snap["result"]["content"][0]["text"])

                # 2. Checkpoint with missing active_task should fail
                res_missing_field = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "context_checkpoint",
                        "arguments": {
                            "project_scope": "demo",
                            "repo_path": str(repo),
                            "agent": "test-agent",
                            "label": "fail-cp-2",
                            "snapshot": {"next_action": "n"},
                        },
                    },
                })
                self.assertTrue(res_missing_field["result"]["isError"])
                self.assertIn("invalid_snapshot_active_task", res_missing_field["result"]["content"][0]["text"])

                # 3. Valid Checkpoint
                res_cp = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "name": "context_checkpoint",
                        "arguments": {
                            "project_scope": "demo",
                            "repo_path": str(repo),
                            "agent": "test-agent",
                            "label": "success-cp",
                            "snapshot": {"active_task": "Refactor architecture", "next_action": "Write tests"},
                            "decisions": [{
                                "title": "Store Format",
                                "decision": "JSONL records",
                                "rationale": "Append-friendly durability",
                                "status": "agent_inferred",
                            }],
                        },
                    },
                })
                self.assertFalse(res_cp["result"]["isError"])
                cp_data = json.loads(res_cp["result"]["content"][0]["text"])["result"]
                self.assertTrue(cp_data["written"])

                # 4. Resume with invalid token budget
                res_bad_budget = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {
                        "name": "context_resume",
                        "arguments": {"project_scope": "demo", "repo_path": str(repo), "max_tokens": 100},
                    },
                })
                self.assertTrue(res_bad_budget["result"]["isError"])
                self.assertIn("invalid_token_budget", res_bad_budget["result"]["content"][0]["text"])

                # 5. Valid Resume
                res_resume = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 14,
                    "method": "tools/call",
                    "params": {
                        "name": "context_resume",
                        "arguments": {"project_scope": "demo", "repo_path": str(repo), "max_tokens": 5000},
                    },
                })
                self.assertFalse(res_resume["result"]["isError"])
                resume_data = json.loads(res_resume["result"]["content"][0]["text"])["result"]
                self.assertTrue(resume_data["ready"])
                self.assertEqual(resume_data["context"]["decisions"][0]["title"], "Store Format")

                # 6. Valid Handoff
                res_handoff = mcp._reply({
                    "jsonrpc": "2.0",
                    "id": 15,
                    "method": "tools/call",
                    "params": {
                        "name": "context_handoff",
                        "arguments": {
                            "project_scope": "demo",
                            "repo_path": str(repo),
                            "source_agent": "agent-1",
                            "target_agent": "agent-2",
                            "task_summary": "Handoff to agent 2",
                        },
                    },
                })
                self.assertFalse(res_handoff["result"]["isError"])
                handoff_data = json.loads(res_handoff["result"]["content"][0]["text"])["result"]
                self.assertTrue(handoff_data["written"])
                self.assertTrue(handoff_data["handoff_id"].startswith("handoffrecord-"))

            finally:
                hs.HANDOFFSTONE_DIR = old_hs_dir
                if old_store is not None:
                    os.environ["HANDOFFSTONE_HOME"] = old_store
                else:
                    os.environ.pop("HANDOFFSTONE_HOME", None)
                if old_root is not None:
                    os.environ["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = old_root
                else:
                    os.environ.pop("HANDOFFSTONE_ALLOWED_REPO_ROOT", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
