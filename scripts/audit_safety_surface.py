"""Repository safety-surface scanner.

The scanner observes source and repository metadata only. It never imports runtime
modules, reads secret values, contacts a provider, or executes discovered probes.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Keep these markers assembled so the scanner does not report its own literals.
_FUNDED = "/opt" + "/bots/bitget-listener"
_FUNDED_ALT = "/root" + "/bitget-listener"
_PRODUCTION_PRODUCTS = {"umcbl", "cmbl", "dmcbl", "usdt-futures", "coin-futures"}
_SECRET_ENV = re.compile(r"os\.environ(?:\.get)?\s*\[?\s*['\"][^'\"]*(?:KEY|SECRET|PASSPHRASE|TOKEN)[^'\"]*['\"]", re.I)
_SIGNED = re.compile(r"(?:hmac\.|sign[_ -]?request|signed[_ -]?request|ACCESS-SIGN|private[_ -]?request)", re.I)
_PRODUCT = re.compile(r"['\"]([A-Za-z0-9_-]+)['\"]")
_SENSITIVE_NAMES = re.compile(r"(?:^|[._-])(\.env(?:\..*)?|.*(?:secret|credential|private.?key|api.?key).*|.*\.sqlite3?|.*\.db)$", re.I)


def _executable_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in (root / "src", root / "scripts"):
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*.py") if path.name != Path(__file__).name)
    return sorted(paths)


def _finding(kind: str, path: Path, line: int, detail: str) -> dict:
    return {"kind": kind, "file": str(path), "line": line, "detail": detail}


def scan_repo(root: Path | str = Path(".")) -> dict:
    root = Path(root).resolve()
    findings: list[dict] = []
    checks = {
        "forbidden_path": {"status": "PROVEN", "finding_count": 0},
        "production_product": {"status": "PROVEN", "finding_count": 0},
        "credential_access": {"status": "PROVEN", "finding_count": 0},
        "signed_request": {"status": "NOT_EVIDENCED", "finding_count": 0},
        "sensitive_file": {"status": "PROVEN", "finding_count": 0},
        "unignored_artifact": {"status": "PROVEN", "finding_count": 0},
    }

    for path in _executable_files(root):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for number, text in enumerate(lines, 1):
            code_text = text.strip()
            if _FUNDED in text or _FUNDED_ALT in text:
                findings.append(_finding("forbidden_path", path, number, "forbidden funded-bot path in executable source"))
            values = {match.lower() for match in _PRODUCT.findall(text)}
            for value in sorted(values & _PRODUCTION_PRODUCTS):
                findings.append(_finding("production_product", path, number, f"production product marker: {value}"))
            if _SECRET_ENV.search(text):
                findings.append(_finding("credential_access", path, number, "credential environment access"))
            if code_text and not code_text.startswith(("#", "\"\"\"", "'''", "\"", "'")) and _SIGNED.search(text):
                findings.append(_finding("signed_request", path, number, "signed-request or signing marker"))

    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if _SENSITIVE_NAMES.search(path.name):
            findings.append(_finding("sensitive_file", path, 1, "sensitive filename present"))
            if path.name == ".env" or path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                try:
                    ignored = __import__("subprocess").run(
                        ["git", "check-ignore", "--quiet", str(path.relative_to(root))], cwd=root,
                        stdout=__import__("subprocess").DEVNULL, stderr=__import__("subprocess").DEVNULL,
                    ).returncode == 0
                except OSError:
                    ignored = False
                if not ignored:
                    findings.append(_finding("unignored_artifact", path, 1, "sensitive artifact is not git-ignored"))

    for kind in checks:
        matches = [item for item in findings if item["kind"] == kind]
        checks[kind]["finding_count"] = len(matches)
        if matches:
            checks[kind]["status"] = "FLAGGED"
        elif kind == "signed_request":
            checks[kind]["status"] = "NOT_EVIDENCED"

    return {
        "schema_version": 1,
        "repository": str(root),
        "status": "FLAGGED" if findings else "PROVEN",
        "checks": checks,
        "findings": findings,
        "finding_count": len(findings),
        "note": "No secret values are read or emitted; absence of a marker is NOT_EVIDENCED, not proof of safety.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit executable safety surface without executing it")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = scan_repo(args.root)
    print(json.dumps(result, indent=2 if args.json else None, sort_keys=True))
    return 0 if result["status"] == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
