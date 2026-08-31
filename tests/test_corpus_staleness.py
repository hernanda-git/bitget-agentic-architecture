"""Fail-closed corpus-staleness observation (TDD, mutation-verified).

The autonomous heartbeat must watch corpus staleness honestly (directive §7):
a missing or unreadable corpus is reported STALE, never "fresh". The honest
acquisition timestamp is each dataset's ``fetched_at_ms`` (written by
``acquire_corpus``), never the wall clock at read time.
"""
from pathlib import Path

from src.evaluation.corpus_staleness import (
    DEFAULT_MAX_AGE_MS,
    CorpusFreshness,
    evaluate_corpus_freshness,
)

# Realistic epoch-ms (year ~2023) so fetched_at_ms stays a positive int.
NOW = 1_700_000_000_000


def _dataset(path: Path, fetched_at_ms: int) -> None:
    path.write_text(f'{{"symbol": "BTCUSDT", "fetched_at_ms": {fetched_at_ms}}}')


def test_missing_corpus_reports_stale_fail_closed(tmp_path):
    corpus = tmp_path / "absent"
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    assert result.present is False
    assert result.datasets == 0
    assert result.newest_ms is None
    assert result.stale is True
    assert result.reason == "no_fresh_corpus"


def test_fresh_dataset_reports_fresh(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    _dataset(corpus / "BTCUSDT_1m.json", NOW - 1000)
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    assert result.present is True
    assert result.datasets == 1
    assert result.newest_ms == NOW - 1000
    assert result.fresh_ms == 1000
    assert result.stale is False
    assert result.reason == "fresh"


def test_stale_dataset_reports_stale(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    old = NOW - (DEFAULT_MAX_AGE_MS + 1)
    _dataset(corpus / "BTCUSDT_1m.json", old)
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    assert result.present is True
    assert result.datasets == 1
    assert result.newest_ms == old
    assert result.fresh_ms == DEFAULT_MAX_AGE_MS + 1
    assert result.stale is True
    assert result.reason == "stale"


def test_unreadable_file_excluded_and_still_stale(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    (corpus / "corrupt.json").write_text("{not valid json")
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    # A corrupt/unreadable file must NOT be invented into "fresh".
    assert result.present is False
    assert result.datasets == 0
    assert result.stale is True
    assert result.reason == "no_fresh_corpus"


def test_manifest_without_fetched_at_does_not_make_corpus_fresh(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    (corpus / "corpus_manifest.json").write_text(
        '{"generated_at_ms": 999999, "datasets": []}')
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    # Manifest alone (no dataset carrying fetched_at_ms) is not a fresh corpus.
    assert result.present is False
    assert result.stale is True


def test_newest_and_oldest_tracked_across_datasets(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    _dataset(corpus / "BTCUSDT_1m.json", NOW - 5000)   # older
    _dataset(corpus / "ETHUSDT_1m.json", NOW - 1000)  # newer
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    assert result.datasets == 2
    assert result.newest_ms == NOW - 1000
    assert result.oldest_ms == NOW - 5000
    assert result.fresh_ms == 1000
    assert result.stale is False


def test_as_dict_round_trips_fields(tmp_path):
    corpus = tmp_path / "history"
    corpus.mkdir()
    _dataset(corpus / "BTCUSDT_1m.json", NOW - 1000)
    result = evaluate_corpus_freshness(corpus, now_ms=NOW, max_age_ms=DEFAULT_MAX_AGE_MS)
    d = result.as_dict()
    assert d["stale"] is False
    assert d["datasets"] == 1
    assert d["newest_ms"] == NOW - 1000
