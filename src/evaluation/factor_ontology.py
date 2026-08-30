"""Machine-readable mirror of the directive sec. 3 factor ontology.

The `AUTONOMOUS_BITCOIN_ADAPTATION_DIRECTIVE.md` (sec. 3) defines the factor
space as a *living knowledge base* the agent must "continuously extend,
challenge, and prune." This module makes that prose canonical and machine-readable
so coverage gaps relative to the ontology are auditable and a promotion claim
cannot be made while entire categories remain unrepresented.

The seven keys below MUST stay in sync with directive sec. 3. If the directive is
edited, this dict is the single source of truth in code and the tests
(``test_ontology_mirrors_directive_seven_categories``) will fail until both agree.
"""
from __future__ import annotations

from typing import Iterable

# Canonical factor ontology — mirror of directive sec. 3.
# Keys are the canonical category identifiers; values enumerate concrete factors.
FACTOR_CATEGORIES: dict[str, tuple[str, ...]] = {
    "macro_liquidity": (
        "rates", "DXY", "real_yields", "CPI_employment_cycles",
        "cb_balance_sheets", "usd_liquidity", "risk_on_off",
    ),
    "onchain": (
        "exchange_in_out_flows", "stablecoin_supply", "holder_cost_bases",
        "MVRV_NUPL", "miner_behavior", "whale_wallets", "HODL_waves",
    ),
    "derivatives_microstructure": (
        "perp_funding", "open_interest", "basis", "liquidation_cascades",
        "OI_volume_divergence", "book_depth", "spread_slippage", "venue_inventory",
    ),
    "flow_participation": (
        "spot_vs_derivative_split", "ETF_flows", "stablecoin_mint_burn",
        "cross_venue_arb_pressure",
    ),
    "sentiment_attention": (
        "social_volume", "fear_greed", "news_shock_absorption", "narrative_cycles",
    ),
    "time_structure": (
        "sessions_asia_ny_london", "expiries", "halving_cycle_seasonality",
        "liquidity_droughts",
    ),
    "adversarial": (
        "bot_crowding", "spoofing_layering", "liquidation_hunts",
        "extraction_by_other_bots",
    ),
}

_PRESENT = frozenset(FACTOR_CATEGORIES.keys())


class FactorOntologyError(ValueError):
    """Raised when a factor category is unknown to the ontology (fail-closed)."""


def normalize_category(category: str) -> str:
    """Return the canonical category key or raise ``FactorOntologyError``.

    Fail-closed: unknown input is never coerced into a real bucket.
    """
    if category not in _PRESENT:
        raise FactorOntologyError(f"unknown factor category: {category!r}")
    return category


def coverage_summary(registry: "object") -> dict:
    """Summarize how many ontology categories are represented by hypotheses.

    ``registry`` must expose ``__iter__`` yielding ``Hypothesis`` objects that
    carry a ``category`` attribute. The returned dict is fail-closed: an empty or
    partially-covered registry is never ``promotion_ready``.
    """
    represented: set[str] = set()
    for hypothesis in registry:  # type: ignore[attr-defined]
        cat = getattr(hypothesis, "category", "") or ""
        if cat in _PRESENT:
            represented.add(cat)
    unrepresented = set(_PRESENT) - represented
    return {
        "total_categories": len(_PRESENT),
        "represented_count": len(represented),
        "represented_categories": sorted(represented),
        "unrepresented_count": len(unrepresented),
        "unrepresented_categories": sorted(unrepresented),
        "promotion_ready": len(unrepresented) == 0,
    }


def all_categories(registry: "object") -> set[str]:
    """Return the set of canonical categories used by a registry's hypotheses."""
    seen: set[str] = set()
    for hypothesis in registry:  # type: ignore[attr-defined]
        cat = getattr(hypothesis, "category", "") or ""
        if cat in _PRESENT:
            seen.add(cat)
    return seen


def list_factors(category: str) -> tuple[str, ...]:
    """Return the concrete factors enumerated under a canonical category.

    Fail-closed: an unknown category raises ``FactorOntologyError`` rather than
    returning an empty/default list.
    """
    cat = normalize_category(category)
    return FACTOR_CATEGORIES[cat]


def validate_factor(category: str, factor: str) -> str:
    """Return ``factor`` if it is a member of the given canonical category.

    Fail-closed: an unknown category raises ``FactorOntologyError``, and a factor
    that is listed under a *different* category is rejected (never coerced or
    aliased into the requested category). This makes each concrete factor
    first-class and challengeable per directive sec. 3.
    """
    cat = normalize_category(category)
    if factor not in FACTOR_CATEGORIES[cat]:
        raise FactorOntologyError(
            f"factor {factor!r} is not a member of category {cat!r}"
        )
    return factor

