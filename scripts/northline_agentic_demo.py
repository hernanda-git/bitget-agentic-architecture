"""Standalone, offline-safe composition root for the Northline demo.

This launcher intentionally composes only the repository's fake paper and shadow
runners. It has no live exchange, account, or funds-moving mode.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))


def _load_runner(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load standalone runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Northline standalone demo launcher (shadow by default; paper is offline fake execution)"
    )
    parser.add_argument("--mode", default="shadow", help="shadow (default) or paper")
    parser.add_argument("--status", action="store_true", help="print standalone capability status and exit")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT"])
    parser.add_argument("--scenario", choices=["hold", "enter"], default="hold")
    parser.add_argument("--ledger", default="data/northline-agentic-demo.sqlite3")
    parser.add_argument("--reports-dir", default="reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps({
            "name": "northline-agentic-demo",
            "mode": "standalone",
            "default_mode": "shadow",
            "ui_bind": os.environ.get("DEMO_BIND_HOST", "127.0.0.1"),
            "network_calls": 0,
            "signed_calls": 0,
            "capabilities": ["observe", "offline-paper"],
        }, sort_keys=True))
        return 0
    if args.mode not in {"shadow", "paper"}:
        parser.error(f"mode {args.mode!r} is not supported by the standalone demo")
    if args.mode == "paper" and os.environ.get("DEMO_EXECUTION_CONFIRM") != "I_UNDERSTAND_DEMO_EXECUTION":
        parser.error("paper demo execution requires DEMO_EXECUTION_CONFIRM=I_UNDERSTAND_DEMO_EXECUTION")

    if args.mode == "shadow":
        runner = _load_runner("run_autonomous_shadow.py")
        report = runner.run_shadow(args.cycles, [s.strip().upper() for value in args.symbols for s in value.split(",") if s.strip()], Path(args.ledger), Path(args.reports_dir))
    else:
        runner = _load_runner("run_autonomous_paper.py")
        symbols = [s.strip().upper() for value in args.symbols for s in value.split(",") if s.strip()]
        report = runner.run_paper(args.cycles, symbols, Path(args.ledger), Path(args.reports_dir), args.scenario)
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("integrity_ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
