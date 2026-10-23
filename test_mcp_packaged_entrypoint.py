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


if __name__ == "__main__":
    unittest.main(verbosity=2)
