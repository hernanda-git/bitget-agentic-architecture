import json
import subprocess
import sys


def run_cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "scripts/run_autonomous_paper.py", *args],
        cwd=".", text=True, capture_output=True,
    )


def test_paper_cli_bounded_run_writes_json_and_markdown_report(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(tmp_path, "--mode", "paper", "--cycles", "2", "--symbols", "BTCUSDT",
                     "--ledger", str(tmp_path / "ledger.sqlite3"), "--reports-dir", str(reports))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["mode"] == "paper"
    assert summary["cycles_requested"] == 2
    assert summary["cycles_completed"] == 2
    assert summary["integrity_ok"] is True
    json_report = reports / f"run-{summary['run_id']}.json"
    md_report = reports / f"run-{summary['run_id']}.md"
    assert json_report.exists() and md_report.exists()
    report = json.loads(json_report.read_text())
    assert report["counts"]["cycles"] == 2
    assert "rejection_codes" in report
    assert "provider" in report
    assert "fee_inclusive_outcome" in report


def test_paper_cli_closes_enter_position_before_success(tmp_path):
    result = run_cli(tmp_path, "--mode", "paper", "--cycles", "1", "--symbols", "BTCUSDT",
                     "--scenario", "enter", "--ledger", str(tmp_path / "ledger.sqlite3"),
                     "--reports-dir", str(tmp_path / "reports"))
    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["integrity_ok"] is True
    assert summary["open_positions"] == []
    assert summary["closed_trades"]


def test_paper_cli_rejects_live_mode(tmp_path):
    result = run_cli(tmp_path, "--mode", "live", "--ledger", str(tmp_path / "ledger.sqlite3"))
    assert result.returncode != 0
    assert "paper" in (result.stderr + result.stdout).lower()


def test_paper_cli_accepts_space_separated_symbols(tmp_path):
    result = run_cli(tmp_path, "--mode", "paper", "--cycles", "1", "--symbols", "BTCUSDT", "ETHUSDT",
                     "--ledger", str(tmp_path / "ledger.sqlite3"), "--reports-dir", str(tmp_path / "reports"))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["cycles_requested"] == 2
    assert summary["cycles_completed"] == 2
