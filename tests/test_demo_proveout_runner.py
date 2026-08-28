"""Runner-level safety checks for the gated demo prove-out (no network egress).

These prove the runner refuses unsafe configurations BEFORE any transport call:
* a production host is refused by defense-in-depth (_validate_host);
* DEMO_EXECUTION_CONFIRM=1 is required.
The BitgetDemoAdapter's own production/live/withdrawal gates are covered in
tests/test_demo_adapter_gates.py. Here we exercise the RUNNER's pre-checks.
"""
from __future__ import annotations

import os
import subprocess
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_demo_proveout.py"


def _run(env, *cli_args):
    return subprocess.run(
        [sys.executable, str(RUNNER), *cli_args],
        env={**os.environ, **env}, capture_output=True, text=True,
    )


def test_production_host_refused_before_any_transport():
    # Stored .env points BITGET_REST_BASE at production; the runner must refuse
    # before constructing a transport. No network egress occurs.
    env = {
        "DEMO_EXECUTION_CONFIRM": "1",
        "BITGET_REST_BASE": "https://api.bitget.com",
        "BITGET_API_KEY": "dummy",
        "BITGET_API_SECRET": "dummy",
        "BITGET_PASSPHRASE": "dummy",
    }
    proc = _run(env, "--symbol", "BTCUSDT")
    assert proc.returncode != 0
    assert "non-demo host" in (proc.stdout + proc.stderr).lower()


def test_missing_confirm_gate_refused():
    env = {
        "BITGET_REST_BASE": "https://demo-api.bitget.com",
        "BITGET_API_KEY": "dummy",
        "BITGET_API_SECRET": "dummy",
        "BITGET_PASSPHRASE": "dummy",
    }
    # No DEMO_EXECUTION_CONFIRM -> argparse error (returncode 2).
    proc = _run(env, "--symbol", "BTCUSDT")
    assert proc.returncode != 0


def test_missing_credentials_refused():
    env = {"DEMO_EXECUTION_CONFIRM": "1", "BITGET_REST_BASE": "https://demo-api.bitget.com"}
    proc = _run(env, "--symbol", "BTCUSDT")
    assert proc.returncode != 0
    assert "missing environment variable" in (proc.stdout + proc.stderr)
