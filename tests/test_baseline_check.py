from pathlib import Path

from scripts.baseline_check import collect_baseline, parse_collected_count


def test_collect_baseline_is_structured_and_redacts_secrets(tmp_path: Path):
    result = collect_baseline(tmp_path / "repo")
    assert set(("revision", "git_status", "test_count", "compile_ok", "boundary_ok", "secrets_found")) <= result.keys()
    assert result["secrets_found"] == []
    assert isinstance(result["test_count"], int)


def test_parse_collected_count_understands_modern_pytest_summary():
    # Modern pytest -q prints "<N> tests collected in <t>s" after the test ids.
    output = "tests/test_a.py::test_one\ntests/test_a.py::test_two\n\n248 tests collected in 0.19s\n"
    assert parse_collected_count(output) == 248


def test_parse_collected_count_understands_legacy_pytest_summary():
    output = "collected 153 items\ntests/test_a.py::test_one\n"
    assert parse_collected_count(output) == 153


def test_parse_collected_count_falls_back_to_counting_test_ids():
    output = "tests/test_a.py::test_one\ntests/test_b.py::test_two\nno summary line here\n"
    assert parse_collected_count(output) == 2
