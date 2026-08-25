import json
import shutil
from pathlib import Path

from scripts.verify_phase5_report import validate_phase5_report


ROOT = Path(__file__).resolve().parents[1]


def test_phase5_report_validator_accepts_synchronized_artifacts():
    assert validate_phase5_report(ROOT) == []


def test_phase5_report_validator_rejects_stale_markdown(tmp_path):
    reports = tmp_path / "reports" / "phase-5"
    reports.mkdir(parents=True)
    for name in ("baseline.json", "summary.json", "summary.md"):
        shutil.copy(ROOT / "reports/phase-5" / name, reports / name)
    baseline = json.loads((reports / "baseline.json").read_text())
    value = str(baseline["walk_forward_evaluation"][0]["net_pnl"])
    markdown = (reports / "summary.md").read_text()
    (reports / "summary.md").write_text(markdown.replace(value, "0", 1))

    errors = validate_phase5_report(tmp_path)

    assert any("walk-forward net PnL" in error for error in errors)


def test_phase5_report_validator_rejects_summary_json_drift(tmp_path):
    reports = tmp_path / "reports" / "phase-5"
    reports.mkdir(parents=True)
    for name in ("baseline.json", "summary.json", "summary.md"):
        shutil.copy(ROOT / "reports/phase-5" / name, reports / name)
    summary_path = reports / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["net_pnl"] = 0
    summary_path.write_text(json.dumps(summary))

    errors = validate_phase5_report(tmp_path)

    assert any("net_pnl" in error for error in errors)


def test_phase5_report_validator_rejects_missing_spread_attribution(tmp_path):
    reports = tmp_path / "reports" / "phase-5"
    reports.mkdir(parents=True)
    for name in ("baseline.json", "summary.json", "summary.md"):
        shutil.copy(ROOT / "reports/phase-5" / name, reports / name)
    baseline = json.loads((reports / "baseline.json").read_text())
    claim = f"- Spread: `{baseline['spread']}`"
    markdown = (reports / "summary.md").read_text()
    (reports / "summary.md").write_text(markdown.replace(claim, "", 1))

    errors = validate_phase5_report(tmp_path)

    assert any("spread" in error for error in errors)
