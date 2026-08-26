import json
from pathlib import Path

import scripts.audit_safety_surface as audit

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_reports_structured_boundary_findings(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "unsafe.py").write_text(
        "import os\n"
        "TOKEN = os.environ['BITGET_API_KEY']\n"
        "path = '/opt/bots/bitget-listener'\n"
        "product = 'umcbl'\n"
        "def sign_request(): pass\n"
    )
    (tmp_path / ".env").write_text("SECRET=not-readable-by-scanner\n")
    result = audit.scan_repo(tmp_path)
    assert result["status"] == "FLAGGED"
    kinds = {finding["kind"] for finding in result["findings"]}
    assert {"forbidden_path", "production_product", "credential_access", "signed_request", "sensitive_file"} <= kinds
    assert all("not-readable-by-scanner" not in json.dumps(finding) for finding in result["findings"])
    assert all("file" in finding and "line" in finding for finding in result["findings"])


def test_scanner_reports_proven_and_not_evidenced_states(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "safe.py").write_text("MODE = 'paper'\n")
    result = audit.scan_repo(tmp_path)
    assert result["status"] == "PROVEN"
    assert result["checks"]["forbidden_path"]["status"] == "PROVEN"
    assert result["checks"]["signed_request"]["status"] == "NOT_EVIDENCED"


def test_scanner_cli_emits_json(tmp_path, capsys):
    (tmp_path / "src").mkdir()
    assert audit.main(["--root", str(tmp_path), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["repository"] == str(tmp_path)
    assert output["status"] == "PROVEN"


def test_signed_probe_scripts_are_not_in_normal_surface():
    probe_names = {
        "demo_smoke_order.py",
        "bitget_demo_probe.py",
        "bitget_demo_mode_probe.py",
        "demo_account_mode_probe.py",
        "demo_position_probe.py",
    }
    assert not any((ROOT / "scripts" / name).exists() for name in probe_names)
    assert all((ROOT / "quarantine" / "demo-probes" / name).is_file() for name in probe_names)
    assert (ROOT / "docs" / "PROBE_QUARANTINE.md").is_file()
