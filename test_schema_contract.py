"""Validate the published schema against real canonical package exports.

Run with: python -m pip install 'jsonschema>=4,<5>' && python test_schema_contract.py
The runtime library itself remains dependency-free.
"""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
import handoffstone as hs


class SchemaContractTests(unittest.TestCase):
    def test_canonical_context_package_with_conversation_evidence(self):
        evidence = hs.EvidenceReference(
            id="source-1",
            kind="conversation",
            locator="conversation-id",
            description="Source message",
        )
        project = hs.create_record(
            hs.RecordKind.PROJECT_CONTEXT,
            project_scope="demo",
            created_by="schema-test",
            name="demo",
        )
        decision = hs.create_record(
            hs.RecordKind.DECISION_RECORD,
            project_scope="demo",
            created_by="schema-test",
            title="SQLite",
            decision="Use SQLite",
            evidence=[evidence],
        )
        pkg = hs.ContextPackage(
            project_context=project, decisions=[decision], evidence=[evidence]
        )
        schema = json.loads(
            (Path(__file__).resolve().parent / "schema" / "handoff.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(pkg.to_dict())


if __name__ == "__main__":
    unittest.main()
