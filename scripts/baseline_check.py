"""Collect a truthful, standalone repository baseline without touching live bot trees."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = ("/opt/bots/" + "bitget-listener", "/root/" + "bitget-listener")
SECRET_MARKERS = ("BITGET_API_KEY" + "=", "BITGET_SECRET" + "=", "BITGET_PASSPHRASE" + "=", "TG_BOT_TOKEN" + "=")


def _run(command: list[str], cwd: Path) -> tuple[int, str]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return completed.returncode, (completed.stdout + completed.stderr)[-12000:]


def _test_count(root: Path) -> int:
    if not (root / "tests").is_dir():
        return 0
    code, output = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"], root)
    if code not in (0, 5):
        return 0
    return parse_collected_count(output) or 0


def parse_collected_count(output: str) -> int | None:
    """Parse the collected-test count from pytest output, both summary styles."""
    for pattern in (r"collected\s+(\d+)\s+items?", r"(\d+)\s+tests?\s+collected"):
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
    counted = sum(1 for line in output.splitlines() if "::" in line and line.strip().startswith("tests/"))
    return counted or None


def _boundary_findings(root: Path) -> list[str]:
    findings: list[str] = []
    for base in (root / "src", root / "scripts"):
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_PATHS + SECRET_MARKERS:
                if marker in text:
                    findings.append(f"{path.relative_to(root)}:{marker}")
    return findings


def collect_baseline(root: Path = ROOT) -> dict:
    root = Path(root)
    if not root.is_dir():
        return {"revision": "unavailable", "git_status": [], "test_count": 0, "compile_ok": False, "boundary_ok": True, "secrets_found": []}
    rev_code, revision = _run(["git", "rev-parse", "HEAD"], root)
    status_code, status = _run(["git", "status", "--short"], root)
    compile_code, _ = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], root)
    findings = _boundary_findings(root)
    return {
        "revision": revision.strip() if rev_code == 0 else "unavailable",
        "git_status": [line for line in status.splitlines() if line.strip()] if status_code == 0 else ["git status unavailable"],
        "test_count": _test_count(root),
        "compile_ok": compile_code == 0,
        "boundary_ok": not findings,
        "secrets_found": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect standalone project baseline evidence")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = collect_baseline()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["compile_ok"] and result["boundary_ok"] and not result["secrets_found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
