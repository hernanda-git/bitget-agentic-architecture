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
    assert str(ROOT) in text
    forbidden_repo = "/opt/bots/" + "bitget-listener"
    assert forbidden_repo not in text
    assert "ExecStart=" in text
    assert "--mode shadow" in text
    assert "127.0.0.1" in text
    assert "EnvironmentFile=-" + str(ROOT / ".env") in text
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


def test_launcher_rejects_production_and_capability_modes():
    for mode in ("live", "transfer", "withdraw"):
        result = subprocess.run([sys.executable, str(LAUNCHER), "--mode", mode], cwd=ROOT,
                                text=True, capture_output=True, timeout=20)
        assert result.returncode != 0
        assert "not supported" in result.stderr.lower()
