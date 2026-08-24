#!/usr/bin/env python3
"""Run the Phase G offline self-review against JSON artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct execution from the repository root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.reviews.runtime_review import review_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Review an offline runtime report and ledger")
    parser.add_argument("report", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = review_run(args.report, args.ledger).to_dict()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
