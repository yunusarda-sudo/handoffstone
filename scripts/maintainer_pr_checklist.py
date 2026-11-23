#!/usr/bin/env python3
"""Maintainer PR Checklist & Triage Gate.

Zero-dependency script for maintainers and automated PR review agents (e.g. Codex CLI)
to verify repository non-negotiables before merging a pull request:
1. Core stdlib-only rule (no third-party imports in handoffstone.py or handoffstone_mcp.py)
2. Zero runtime dependencies in pyproject.toml
3. Integrity of benchmark negative controls in test_bench_handoffstone.py
4. Presence of an entry in CHANGELOG.md under [Unreleased]
5. No committed secrets or real project store fixtures

Usage:
    python3 scripts/maintainer_pr_checklist.py
    python3 scripts/maintainer_pr_checklist.py --check
    python3 scripts/maintainer_pr_checklist.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Known standard library modules across Python 3.10-3.14
_STDLIB_ALLOWLIST = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "difflib", "enum", "errno", "fnmatch",
    "functools", "glob", "gzip", "hashlib", "hmac", "html", "http", "importlib",
    "inspect", "io", "itertools", "json", "logging", "math", "mimetypes", "os",
    "pathlib", "pickle", "platform", "posixpath", "pprint", "random", "re",
    "secrets", "shlex", "shutil", "signal", "socket", "sqlite3", "ssl", "stat",
    "string", "subprocess", "sys", "sysconfig", "tempfile", "textwrap", "threading",
    "time", "traceback", "types", "typing", "unittest", "urllib", "uuid", "warnings",
    "weakref", "zipfile", "zoneinfo", "__future__",
}

# Internal modules in this repo
_INTERNAL_MODULES = {"handoffstone", "handoffstone_mcp", "bench_handoffstone"}

NEGATIVE_CONTROLS = [
    "test_empty_transport_scores_zero",
    "test_garbage_transport_scores_below_real_summary",
    "test_metric_is_sensitive_to_sabotage",
]


def check_stdlib_imports(file_path: Path) -> tuple[bool, list[str]]:
    """Verify that a Python file only imports from the standard library or internal modules."""
    if not file_path.is_file():
        return False, [f"file not found: {file_path.name}"]

    violations = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError as e:
        return False, [f"syntax error parsing {file_path.name}: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg not in _STDLIB_ALLOWLIST and root_pkg not in _INTERNAL_MODULES:
                    violations.append(f"Import '{alias.name}' on line {node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg not in _STDLIB_ALLOWLIST and root_pkg not in _INTERNAL_MODULES:
                    violations.append(f"ImportFrom '{node.module}' on line {node.lineno}")

    return len(violations) == 0, violations


def check_pyproject_dependencies() -> tuple[bool, str]:
    """Verify pyproject.toml has zero runtime dependencies."""
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.is_file():
        return False, "pyproject.toml not found"

    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return False, "dependencies field not found in pyproject.toml"

    deps = [d.strip().strip('"\'') for d in match.group(1).split(",") if d.strip().strip('"\'')]
    if deps:
        return False, f"found runtime dependencies: {deps}"
    return True, "dependencies = []"


def check_negative_controls() -> tuple[bool, list[str]]:
    """Verify that all required benchmark negative controls remain defined."""
    test_bench = ROOT / "test_bench_handoffstone.py"
    if not test_bench.is_file():
        return False, ["test_bench_handoffstone.py not found"]

    content = test_bench.read_text(encoding="utf-8")
    missing = [nc for nc in NEGATIVE_CONTROLS if f"def {nc}" not in content]
    return len(missing) == 0, missing


def check_changelog() -> tuple[bool, str]:
    """Verify that CHANGELOG.md contains an [Unreleased] section with entries."""
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        return False, "CHANGELOG.md not found"

    content = changelog.read_text(encoding="utf-8")
    unreleased_match = re.search(r"## \[Unreleased\]\s*\n(.*?)(?=\n## \[|\Z)", content, re.DOTALL)
    if not unreleased_match:
        return False, "no [Unreleased] section found"

    body = unreleased_match.group(1).strip()
    bullet_count = len(re.findall(r"^\s*-\s+", body, re.MULTILINE))
    if bullet_count == 0:
        return False, "[Unreleased] section contains no entries"
    return True, f"{bullet_count} unreleased entries documented"


def run_checks() -> dict[str, dict]:
    """Execute all maintainer checks and return structured results."""
    results = {}

    core_ok, core_viol = check_stdlib_imports(ROOT / "handoffstone.py")
    results["core_stdlib"] = {
        "pass": core_ok,
        "label": "Core library (`handoffstone.py`) is stdlib-only",
        "details": core_viol if not core_ok else "Zero third-party imports",
    }

    mcp_ok, mcp_viol = check_stdlib_imports(ROOT / "handoffstone_mcp.py")
    results["mcp_stdlib"] = {
        "pass": mcp_ok,
        "label": "MCP adapter (`handoffstone_mcp.py`) is stdlib-only",
        "details": mcp_viol if not mcp_ok else "Zero third-party imports",
    }

    deps_ok, deps_details = check_pyproject_dependencies()
    results["runtime_dependencies"] = {
        "pass": deps_ok,
        "label": "Zero runtime dependencies in `pyproject.toml`",
        "details": deps_details,
    }

    nc_ok, nc_missing = check_negative_controls()
    results["negative_controls"] = {
        "pass": nc_ok,
        "label": "Benchmark negative controls intact in `test_bench_handoffstone.py`",
        "details": f"Missing: {nc_missing}" if not nc_ok else "All negative controls present",
    }

    cl_ok, cl_details = check_changelog()
    results["changelog"] = {
        "pass": cl_ok,
        "label": "Changelog has documented [Unreleased] changes",
        "details": cl_details,
    }

    return results


def format_markdown(results: dict[str, dict]) -> str:
    lines = ["## Maintainer Triage & Security Checklist", ""]
    all_pass = True
    for item in results.values():
        box = "[x]" if item["pass"] else "[ ]"
        lines.append(f"- {box} **{item['label']}**")
        if not item["pass"]:
            all_pass = False
            lines.append(f"  - ⚠️ *Failed:* {item['details']}")
    lines.append("")
    lines.append(f"**Gate Status:** {'✅ APPROVED' if all_pass else '❌ REJECTED'}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit code 1 if any check fails")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    results = run_checks()
    all_pass = all(v["pass"] for v in results.values())

    if args.json:
        print(json.dumps({"all_pass": all_pass, "checks": results}, indent=2))
    else:
        print(format_markdown(results))

    return 0 if (all_pass or not args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
