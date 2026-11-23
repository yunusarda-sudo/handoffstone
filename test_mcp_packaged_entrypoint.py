"""Verify the installed wheel exposes a usable MCP stdio command."""
import json
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sysconfig
import tempfile
import unittest


class PackagedMcpEntryPoint(unittest.TestCase):
    def test_initialize_and_discover_tools_outside_source_tree(self):
        executable = Path(sysconfig.get_path("scripts")) / "handoffstone-mcp"
        self.assertTrue(executable.is_file(), "install the built wheel before this check")
        with tempfile.TemporaryDirectory(prefix="handoffstone_mcp_cli_") as tmp:
            root = Path(tmp)
            env = dict(os.environ)
            env["HANDOFFSTONE_HOME"] = str(root / "store")
            env["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = str(root)
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ]
            result = subprocess.run(
                [str(executable)], input="".join(json.dumps(item) + "\n" for item in requests),
                capture_output=True, text=True, cwd=root, env=env, timeout=15,
                check=True,
            )
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(replies), 2, result.stderr)
            info = replies[0]["result"]["serverInfo"]
            self.assertEqual(info["name"], "handoffstone-mcp")
            expected_version = os.environ.get("EXPECTED_VERSION", version("handoffstone"))
            self.assertEqual(info["version"], expected_version)
            self.assertEqual(
                {tool["name"] for tool in replies[1]["result"]["tools"]},
                {"context_checkpoint", "context_resume", "context_handoff"},
            )
            self.assertFalse((root / "store").exists())

    def test_end_to_end_mcp_host_lifecycle(self):
        """Exercise full MCP host lifecycle over stdio against installed wheel."""
        executable = Path(sysconfig.get_path("scripts")) / "handoffstone-mcp"
        self.assertTrue(executable.is_file(), "install the built wheel before this check")
        with tempfile.TemporaryDirectory(prefix="handoffstone_mcp_host_") as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
            (repo / "README.md").write_text("# MCP Lifecycle Test\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init commit"], cwd=repo, check=True, capture_output=True)

            store_dir = root / "store"
            env = dict(os.environ)
            env["HANDOFFSTONE_HOME"] = str(store_dir)
            env["HANDOFFSTONE_ALLOWED_REPO_ROOT"] = str(repo)

            proc = subprocess.Popen(
                [str(executable)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=repo,
            )

            try:
                def rpc(req):
                    proc.stdin.write(json.dumps(req) + "\n")
                    proc.stdin.flush()
                    return json.loads(proc.stdout.readline())

                # 1. Initialize
                init_res = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
                self.assertEqual(init_res["result"]["serverInfo"]["name"], "handoffstone-mcp")
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
                proc.stdin.flush()

                # 2. Checkpoint
                checkpoint_res = rpc({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "context_checkpoint",
                        "arguments": {
                            "project_scope": "mcp-lifecycle",
                            "repo_path": str(repo),
                            "agent": "producer-agent",
                            "label": "initial-checkpoint",
                            "snapshot": {
                                "active_task": "Cross-agent task transfer",
                                "next_action": "Verify resume in consumer",
                            },
                            "decisions": [{
                                "title": "Transport Architecture",
                                "decision": "Use MCP stdio protocol",
                                "rationale": "Enables decision-aware handoffs without proprietary network lock-in",
                                "status": "agent_inferred",
                                "supersedes": [],
                            }],
                        },
                    },
                })
                self.assertFalse(checkpoint_res.get("result", {}).get("isError", False))
                cp_data = json.loads(checkpoint_res["result"]["content"][0]["text"])["result"]
                self.assertTrue(cp_data["written"])
                self.assertEqual(len(cp_data["decision_ids"]), 1)
                checkpoint_id = cp_data["checkpoint_id"]

                # 3. Resume
                resume_res = rpc({
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "context_resume",
                        "arguments": {
                            "project_scope": "mcp-lifecycle",
                            "repo_path": str(repo),
                        },
                    },
                })
                self.assertFalse(resume_res.get("result", {}).get("isError", False))
                resume_data = json.loads(resume_res["result"]["content"][0]["text"])["result"]
                self.assertTrue(resume_data["ready"])
                self.assertEqual(resume_data["checkpoint_id"], checkpoint_id)
                self.assertEqual(resume_data["included_decisions"], 1)
                context = resume_data["context"]
                self.assertEqual(context["decisions"][0]["title"], "Transport Architecture")
                self.assertEqual(context["working_state"]["active_task"], "Cross-agent task transfer")

                # 4. Handoff
                handoff_res = rpc({
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "context_handoff",
                        "arguments": {
                            "project_scope": "mcp-lifecycle",
                            "repo_path": str(repo),
                            "source_agent": "producer-agent",
                            "target_agent": "consumer-agent",
                            "task_summary": "Transfer project context to consumer agent",
                        },
                    },
                })
                self.assertFalse(handoff_res.get("result", {}).get("isError", False))
                handoff_data = json.loads(handoff_res["result"]["content"][0]["text"])["result"]
                self.assertTrue(handoff_data["written"])
                self.assertTrue(handoff_data["handoff_id"].startswith("handoffrecord-"))

                # 5. Security isolation check: unauthorized path rejected
                unauth_res = rpc({
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "context_resume",
                        "arguments": {
                            "project_scope": "mcp-lifecycle",
                            "repo_path": str(root),
                        },
                    },
                })
                self.assertTrue(unauth_res.get("result", {}).get("isError", False))
                err_text = unauth_res["result"]["content"][0]["text"]
                self.assertIn("repo_outside_allowed_root", err_text)
            finally:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                if proc.stdout and not proc.stdout.closed:
                    proc.stdout.close()
                if proc.stderr and not proc.stderr.closed:
                    proc.stderr.close()
                proc.wait(timeout=5)

            # 6. Verify records persisted to store
            store_file = store_dir / "mcp-lifecycle.jsonl"
            self.assertTrue(store_file.is_file())
            records = [json.loads(line) for line in store_file.read_text(encoding="utf-8").splitlines() if line]
            kinds = {r["kind"] for r in records}
            self.assertIn("DecisionRecord", kinds)
            self.assertIn("ContextCheckpoint", kinds)
            self.assertIn("HandoffRecord", kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
