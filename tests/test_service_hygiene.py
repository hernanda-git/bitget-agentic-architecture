from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "deploy" / "northline-agentic-demo.service"
LAUNCHER = ROOT / "scripts" / "northline_agentic_demo.py"


def test_service_isolated_and_safe_by_default():
    text = SERVICE.read_text()
    # The unit must reference a single, concrete install root across every path it
    # declares (WorkingDirectory, EnvironmentFile, ExecStart, ReadWritePaths). This
    # is path-consistency, not a hardcode to this checkout: a deploy at
    # /root/bitget-agentic-architecture is valid and the unit must not be edited to
    # point at a different, unstated location. We assert all declared paths share
    # one absolute install root rather than equaling ROOT (which only this dev box
    # would satisfy and which would drift the test away from the real deploy).
    import re
    # Care: the ExecStart line also contains /usr/bin/env (the interpreter), which is
    # NOT a deployment path and must be excluded from the install-root check.
    path_refs = re.findall(r"(/(?:root|home|opt|srv|var|data)[A-Za-z0-9_./-]*)", text)
    assert path_refs, "service unit declares no absolute paths"
    # Every referenced deployment path must live under one common install root that is
    # at least two levels deep (e.g. /root/bitget-agentic-architecture), so the unit
    # cannot silently split state across two locations (a /root vs /home split would
    # NOT share such a root and must fail). A bare "/" common prefix is rejected.
    roots = [p for p in {p for p in path_refs}]
    common = os.path.commonpath(roots)
    assert common.count("/") >= 2, f"declared paths do not share a deep install root: {common!r}"
    for p in roots:
        assert p.startswith(common + "/") or p == common, f"path {p!r} escapes install root {common!r}"
    forbidden_repo = "/opt/bots/" + "bitget-listener"
    assert forbidden_repo not in text
    assert "ExecStart=" in text
    assert "--mode shadow" in text
    assert "127.0.0.1" in text
    assert "EnvironmentFile=-" in text
    assert "DEMO_EXECUTION_CONFIRM" in text
    assert "transfer" not in text.lower()
    assert "withdraw" not in text.lower()
    assert "SUSDT-" + "FUTURES" not in text


def test_launcher_help_and_status_are_offline():
    for args, expected in [(["--help"], "shadow"), (["--status"], "standalone")]:
        result = subprocess.run([sys.executable, str(LAUNCHER), *args], cwd=ROOT,
                                text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert expected in (result.stdout + result.stderr).lower()


def test_launcher_shadow_mode_runs_without_external_services(tmp_path):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--mode", "shadow", "--cycles", "1",
         "--ledger", str(tmp_path / "shadow.sqlite3"), "--reports-dir", str(tmp_path / "reports")],
        cwd=ROOT, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert '"mode": "shadow"' in result.stdout
    assert '"network_calls": 0' in result.stdout


def test_launcher_paper_execution_requires_explicit_confirmation(tmp_path):
    args = [sys.executable, str(LAUNCHER), "--mode", "paper", "--scenario", "enter",
            "--ledger", str(tmp_path / "paper.sqlite3"), "--reports-dir", str(tmp_path / "reports")]
    blocked = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=20,
                             env={k: v for k, v in os.environ.items() if k != "DEMO_EXECUTION_CONFIRM"})
    assert blocked.returncode != 0
    assert "DEMO_EXECUTION_CONFIRM" in blocked.stderr

    allowed_env = os.environ | {"DEMO_EXECUTION_CONFIRM": "I_UNDERSTAND_DEMO_EXECUTION"}
    allowed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=20, env=allowed_env)
    assert allowed.returncode == 0
    assert '"mode": "paper"' in allowed.stdout


def test_canonical_paper_run_is_bounded_and_emits_phase6_evidence(tmp_path):
    env = os.environ | {"DEMO_EXECUTION_CONFIRM": "I_UNDERSTAND_DEMO_EXECUTION"}
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--mode", "paper", "--cycles", "1",
         "--symbols", "BTCUSDT", "--ledger", str(tmp_path / "paper.sqlite3"),
         "--reports-dir", str(tmp_path / "reports")],
        cwd=ROOT, text=True, capture_output=True, timeout=20, env=env)
    assert result.returncode == 0, result.stderr
    report = __import__("json").loads(result.stdout)
    assert report["network_calls"] == report["signed_calls"] == 0
    assert report["open_positions"] == []
    assert report["timestamp_timezone"] == "Asia/Jakarta"
    assert "raw_ledger_counts" in report and "resource_snapshot" in report


def test_canonical_paper_cycle_bound_is_fail_closed(tmp_path):
    env = os.environ | {"DEMO_EXECUTION_CONFIRM": "I_UNDERSTAND_DEMO_EXECUTION"}
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--mode", "paper", "--cycles", "1001",
         "--ledger", str(tmp_path / "paper.sqlite3")], cwd=ROOT,
        text=True, capture_output=True, timeout=20, env=env)
    assert result.returncode != 0
    assert "cycles" in result.stderr.lower()


def test_launcher_rejects_production_and_capability_modes():
    for mode in ("live", "transfer", "withdraw"):
        result = subprocess.run([sys.executable, str(LAUNCHER), "--mode", mode], cwd=ROOT,
                                text=True, capture_output=True, timeout=20)
        assert result.returncode != 0
        assert "not supported" in result.stderr.lower()
