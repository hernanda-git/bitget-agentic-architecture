import json
import subprocess
import sys


def test_shadow_cli_is_network_free_and_writes_report(tmp_path):
    reports = tmp_path / "reports"
    result = subprocess.run(
        [sys.executable, "scripts/run_autonomous_shadow.py", "--cycles", "2",
         "--symbols", "BTCUSDT,ETHUSDT", "--ledger", str(tmp_path / "shadow.sqlite3"),
         "--reports-dir", str(reports)], cwd=".", text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mode"] == "shadow"
    assert summary["cycles_completed"] == 2
    assert summary["orders_placed"] == 0
    assert summary["signed_calls"] == 0
    assert summary["network_calls"] == 0
    assert (reports / f"run-{summary['run_id']}.json").exists()
    assert (reports / f"run-{summary['run_id']}.md").exists()


def test_shadow_cli_rejects_signed_execution_flag(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/run_autonomous_shadow.py", "--signed"],
        cwd=".", text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "signed" in result.stderr.lower()
