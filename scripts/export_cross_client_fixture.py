#!/usr/bin/env python3
"""Export a deterministic handoff package for live cross-client trials.

Writes under artifacts/cross-client/ (gitignored) unless --out is set.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handoffstone as hs  # noqa: E402
from test_cross_client_fidelity import (  # noqa: E402
    SCOPE,
    _critical_snapshot,
    build_producer_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "cross-client",
        help="Directory for handoff.json, handoff.wire.json, snapshot.json",
    )
    parser.add_argument("--agent", default="cursor-composer", help="created_by / producer id")
    args = parser.parse_args()

    store = Path(tempfile.mkdtemp(prefix="handoffstone_export_"))
    hs.HANDOFFSTONE_DIR = store
    pkg = build_producer_package(args.agent)
    args.out.mkdir(parents=True, exist_ok=True)

    canonical = args.out / "handoff.json"
    wire = args.out / "handoff.wire.json"
    snap = args.out / "snapshot.json"
    meta = args.out / "meta.json"

    canonical.write_text(pkg.to_json(), encoding="utf-8")
    wire.write_text(pkg.to_wire_json(), encoding="utf-8")
    snap.write_text(json.dumps(_critical_snapshot(pkg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    meta.write_text(
        json.dumps(
            {
                "scope": SCOPE,
                "producer_agent": args.agent,
                "package_version": pkg.version,
                "decision_count": len(pkg.decisions),
                "constraint_count": len(pkg.constraints),
                "history_count": len(pkg.supersession_history),
                "store": str(store),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(canonical)
    print(wire)
    print(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
