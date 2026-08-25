from pathlib import Path

from scripts.baseline_check import collect_baseline


def test_collect_baseline_is_structured_and_redacts_secrets(tmp_path: Path):
    result = collect_baseline(tmp_path / "repo")
    assert set(("revision", "git_status", "test_count", "compile_ok", "boundary_ok", "secrets_found")) <= result.keys()
    assert result["secrets_found"] == []
    assert isinstance(result["test_count"], int)
