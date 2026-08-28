"""Fail-closed rollup of per-symbol request evidence for honest reporting (TDD: RED first).

When several per-symbol deterministic-baseline reports are folded into one
multi-symbol aggregate, the combined report must transparently disclose the
TOTAL network activity that produced the evidence, and must prove the run never
signed an exchange call or used credentials. This module rolls the per-symbol
``request_evidence`` blocks into one fail-closed summary.
"""
from __future__ import annotations

import pytest

from src.evaluation.evidence_rollup import roll_up_request_evidence


def _ev(requests=5, successes=5, failures=0, rate_limits=0, retries=0,
        signed_calls=0, credentials_used=False):
    return {
        "requests": requests, "successes": successes, "failures": failures,
        "rate_limits": rate_limits, "retries": retries,
        "signed_calls": signed_calls, "credentials_used": credentials_used,
    }


def test_rollup_sums_unauthenticated_evidence():
    """Two unauthenticated public-fetch reports sum cleanly and stay unauthenticated."""
    rolled = roll_up_request_evidence([_ev(), _ev(requests=7, successes=7)])
    assert rolled["requests"] == 12
    assert rolled["successes"] == 12
    assert rolled["failures"] == 0
    assert rolled["rate_limits"] == 0
    assert rolled["retries"] == 0
    assert rolled["signed_calls"] == 0
    assert rolled["credentials_used"] is False
    assert rolled["all_unauthenticated"] is True


def test_rollup_fails_closed_on_any_signed_call():
    """A single signed call anywhere in the evidence base is a constitutional violation."""
    with pytest.raises(ValueError):
        roll_up_request_evidence([_ev(), _ev(signed_calls=1)])


def test_rollup_fails_closed_on_credentials_used():
    """Any report that used credentials taints the whole rollup fail-closed."""
    with pytest.raises(ValueError):
        roll_up_request_evidence([_ev(), _ev(credentials_used=True)])


def test_rollup_rejects_empty_evidence():
    """No evidence base means nothing to roll up; fail closed rather than invent zeros."""
    with pytest.raises(ValueError):
        roll_up_request_evidence([])
