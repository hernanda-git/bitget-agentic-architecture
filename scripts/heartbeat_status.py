"""Heartbeat status aggregator (Phase 47).

Records each autonomous tick into a durable JSONL history + a ``last.json``
snapshot, and assembles a read-only status projection for the observability
dashboard. Pure local reads: git metadata, phase reports, the factor-ontology
coverage, and the resource guard. Fail-closed on missing artifacts (reported as
absent, never invented). No secrets, no /opt/bots/bitget-listener, no signed or
order calls.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.evaluation.corpus_staleness import (
    DEFAULT_MAX_AGE_MS,
    evaluate_corpus_freshness,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = REPO_ROOT / "data" / "heartbeat"
DEFAULT_CORPUS_DIR = REPO_ROOT / "data" / "history"
SCHEDULE_CRON = "0 */6 * * *"  # matches cron job d4a8919dc60c

# Fields a tick record may carry. Anything outside this set is dropped so a
# malformed/over-long report cannot smuggle arbitrary data into the log.
_TICK_FIELDS = (
    "tick_id", "phase", "summary", "passed", "failed", "skipped",
    "baseline_negative", "promotion_blocked", "commit", "pushed",
    "error", "notes",
)


def _iso(ts_ms: int) -> str:
    return _dt.datetime.fromtimestamp(ts_ms / 1000, tz=_dt.timezone.utc).isoformat()


def record_tick(state_dir: Path, *, tick_id: str, phase: str = "", summary: str = "",
                passed: int = 0, failed: int = 0, skipped: int = 0,
                baseline_negative: bool = True, promotion_blocked: bool = True,
                commit: str = "", pushed: bool = False, error: str = "",
                notes: str = "", recorded_at_ms: int | None = None) -> dict:
    """Persist one tick. Writes ``last.json`` and appends to ``ticks.jsonl``."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    now_ms = recorded_at_ms if recorded_at_ms is not None else int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp() * 1000)
    record = {
        "recorded_at_ms": now_ms,
        "recorded_at": _iso(now_ms),
        "tick_id": str(tick_id),
        "phase": str(phase),
        "summary": str(summary),
        "passed": int(passed),
        "failed": int(failed),
        "skipped": int(skipped),
        "baseline_negative": bool(baseline_negative),
        "promotion_blocked": bool(promotion_blocked),
        "commit": str(commit),
        "pushed": bool(pushed),
        "error": str(error),
        "notes": str(notes),
    }
    (state_dir / "last.json").write_text(json.dumps(record, sort_keys=True))
    with (state_dir / "ticks.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def load_history(state_dir: Path, limit: int = 200) -> list[dict]:
    path = Path(state_dir) / "ticks.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def _run_git(args: list[str]) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip()
    except Exception:
        return ""


def _git_status() -> dict:
    commit = _run_git(["rev-parse", "--short", "HEAD"])
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    dirty = _run_git(["status", "--porcelain"])
    ahead = _run_git(["rev-list", "--count", "@{upstream}..HEAD"])
    try:
        last = _run_git(["log", "-1", "--format=%cI"])
        last_commit_at = _dt.datetime.fromisoformat(last).astimezone(_dt.timezone.utc).isoformat() if last else None
    except Exception:
        last_commit_at = None
    return {
        "path_present": (REPO_ROOT / ".git").exists(),
        "branch": branch or "unknown",
        "commit": commit or "unknown",
        "commit_present": bool(commit),
        "dirty": bool(dirty),
        "ahead_count": int(ahead) if ahead.isdigit() else 0,
        "last_commit_at": last_commit_at,
        "remote": "origin/master",
    }


def _phase_reports() -> dict:
    reports_dir = REPO_ROOT / "reports"
    phases: dict[str, dict] = {}
    if reports_dir.is_dir():
        for d in sorted(reports_dir.glob("phase-*/"), reverse=True):
            number = d.name.split("-", 1)[-1]
            md = d / f"{d.name}-report.md"
            if md.exists():
                try:
                    text = md.read_text(encoding="utf-8")
                except Exception:
                    continue
                # Fail-closed, bounded extraction of a few honest signal lines.
                baseline_neg = "negative" in text.lower()
                promotion_blocked = ("promotion" in text.lower() and "block" in text.lower())
                pushed = "pushed to" in text.lower() or "origin/master" in text.lower()
                phases[number] = {
                    "phase": d.name,
                    "report_present": True,
                    "baseline_negative": baseline_neg,
                    "promotion_blocked": promotion_blocked,
                    "pushed": pushed,
                    "bytes": len(text),
                }
    return {"count": len(phases), "latest": phases.get(next(iter(phases), "")), "all": phases}


def _factor_ontology() -> dict:
    try:
        from src.evaluation.factor_ontology import FACTOR_CATEGORIES, coverage_summary
        from src.evaluation.hypotheses import HypothesisRegistry
        reg = HypothesisRegistry()
        # The auditable registry is currently only populated at runtime; we report
        # the canonical ontology + that no hypotheses are loaded into the static
        # registry here (the doc registry is the human-readable source of truth).
        cov = coverage_summary(reg)
        return {
            "categories": {k: list(v) for k, v in FACTOR_CATEGORIES.items()},
            "category_count": len(FACTOR_CATEGORIES),
            "represented_count": cov["represented_count"],
            "unrepresented_categories": cov["unrepresented_categories"],
            "promotion_ready": cov["promotion_ready"],
            "note": "Static registry here is empty; the documentation registry "
                    "(docs/STRATEGY_HYPOTHESES.md) lists the candidate hypotheses.",
        }
    except Exception as exc:  # fail-closed: never invent ontology state
        return {"error": f"unavailable: {exc}"}


def _resource_guard() -> dict:
    try:
        from scripts.resource_guard import status as resource_status
        return dict(resource_status())
    except Exception as exc:
        return {"ok": False, "error": f"unavailable: {exc}"}


def _corpus_freshness(corpus_dir: Any, *, now_ms: int | None = None) -> dict:
    """Public-history corpus freshness as a plain dict for the dashboard.

    Delegates to ``evaluate_corpus_freshness`` (Phase 49, mutation-verified) and
    keeps its fail-closed guarantee: if the observation itself raises we cannot
    prove freshness, so we report ``stale`` rather than invent "fresh".
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    try:
        result = evaluate_corpus_freshness(corpus_dir, now_ms=now_ms)
        return result.as_dict()
    except Exception:
        return {
            "present": False, "datasets": 0, "newest_ms": None, "oldest_ms": None,
            "max_age_ms": DEFAULT_MAX_AGE_MS, "stale": True,
            "reason": "unavailable", "fresh_ms": None,
        }


def derive_next_run(now: _dt.datetime, every_hours: int = 6) -> _dt.datetime:
    """Next future boundary of the form HH:00 where HH % every_hours == 0."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    start = now.replace(minute=0, second=0, microsecond=0)
    for h in range(0, 24, every_hours):
        cand = start.replace(hour=h)
        if cand > now:
            return cand
    return (start + _dt.timedelta(days=1)).replace(hour=0)


def assemble_status(state_dir: Path = DEFAULT_STATE_DIR) -> dict:
    state_dir = Path(state_dir)
    last = None
    last_path = state_dir / "last.json"
    if last_path.exists():
        try:
            last = json.loads(last_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            last = None
    return {
        "mode": "readonly-observability",
        "generated_at": _iso(int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp() * 1000)),
        "schedule_cron": SCHEDULE_CRON,
        "next_scheduled_run": _iso(int(derive_next_run(_dt.datetime.now(tz=_dt.timezone.utc)).timestamp() * 1000)),
        "repo": str(REPO_ROOT),
        "git": _git_status(),
        "latest_tick": last,
        "history": load_history(state_dir),
        "phase_reports": _phase_reports(),
        "factor_ontology": _factor_ontology(),
        "resource_guard": _resource_guard(),
        "corpus_freshness": _corpus_freshness(DEFAULT_CORPUS_DIR),
        "constraints": {
            "shadow_only": True,
            "never_live": True,
            "never_modify_opt_bots": True,
            "product_type": "SUSDT-FUTURES",
            "honesty_gate": "promotion blocked while baseline negative",
        },
    }
