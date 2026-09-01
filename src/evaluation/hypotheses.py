"""Independent strategy hypothesis registry.

The registry is deliberately separate from strategy selection and evaluation so
hypotheses remain auditable claims rather than hidden tuning configuration.
Each hypothesis is also bound to the directive sec. 3 factor ontology via a
``category`` field, so coverage of the factor space is measurable and promotion
cannot be claimed while whole categories remain unrepresented.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from src.evaluation.factor_ontology import normalize_category

_REQUIRED = ("mechanism", "data", "features", "entry_exit", "cost_edge", "falsification", "failure_modes", "data_exclusions", "oos_gate")

# Canonical measured verdicts of the adaptation loop (directive sec. 5/7):
# keep what survives out-of-sample, kill what doesn't, hold while undecided.
OUTCOME_VERDICTS = frozenset({"keep", "kill", "hold"})


@dataclass(frozen=True)
class Outcome:
    """A fail-closed recorded verdict for a hypothesis in the adaptation loop."""

    verdict: str
    reason: str
    evidence: str = ""


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    title: str
    mechanism: str = ""
    data: str = ""
    features: tuple[str, ...] = ()
    category: str = ""
    documented: bool = False
    entry_exit: str = ""
    cost_edge: str = ""
    falsification: str = ""
    failure_modes: str = ""
    data_exclusions: str = ""
    oos_gate: str = ""

    def validate(self):
        missing = [name for name in _REQUIRED if not getattr(self, name)]
        if missing: raise ValueError("missing hypothesis fields: " + ", ".join(missing))
        if not self.hypothesis_id or not self.title: raise ValueError("hypothesis_id and title are required")
        # Fail closed: a hypothesis must declare a known factor-ontology category.
        if not self.category:
            raise ValueError("hypothesis must declare a factor-ontology category")
        normalize_category(self.category)  # raises FactorOntologyError if unknown
        return self


class HypothesisRegistry:
    def __init__(self):
        self._items = {}
        self._outcomes = {}
    def register(self, hypothesis):
        hypothesis.validate()
        if hypothesis.hypothesis_id in self._items: raise ValueError("duplicate hypothesis_id")
        self._items[hypothesis.hypothesis_id] = hypothesis
    def get(self, hypothesis_id): return self._items.get(hypothesis_id)
    def as_dict(self): return {"hypotheses": [asdict(h) for h in self._items.values()]}
    def __iter__(self): return iter(self._items.values())
    def __len__(self): return len(self._items)

    def mark_outcome(self, hypothesis_id, verdict, reason, evidence=""):
        # Fail closed: a verdict can only be recorded for a registered hypothesis.
        if hypothesis_id not in self._items:
            raise ValueError(f"unknown hypothesis_id: {hypothesis_id!r}")
        # Fail closed: an unrecognized verdict is rejected, never coerced/aliased.
        v = verdict.lower() if isinstance(verdict, str) else ""
        if v not in OUTCOME_VERDICTS:
            raise ValueError(
                f"invalid outcome verdict: {verdict!r} (expected one of {sorted(OUTCOME_VERDICTS)})"
            )
        # Fail closed: every verdict is a decision and must be evidenced; a kill
        # especially so (directive sec. 7 -- kill without sentiment, with reason).
        if not reason or not str(reason).strip():
            raise ValueError("outcome requires a non-empty reason (evidence)")
        self._outcomes[hypothesis_id] = Outcome(v, str(reason).strip(), evidence or "")
    def outcome(self, hypothesis_id):
        return self._outcomes.get(hypothesis_id)
    def outcomes(self):
        return dict(self._outcomes)


# ---- Static hypothesis registry populated from docs/STRATEGY_HYPOTHESES.md ----

DEFAULT_HYPOTHESES: HypothesisRegistry = HypothesisRegistry()
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-001",
    title="Trend persistence after directional impulse",
    mechanism="Trend persistence after directional impulse",
    data="Offline candle history with verified chronology",
    features=("Momentum", "volatility", "regime"),
    category="time_structure",
    documented=True,
    entry_exit="Enter after confirmed directional move; exit at stop or target",
    cost_edge="Expected move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Choppy markets, stale data, spread widening, partial fills",
    data_exclusions="Duplicate, malformed, stale, or incomplete records",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence, no unmodeled funding",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-002",
    title="Holder-cost reversion when MVRV/NUPL signals extremes",
    mechanism="Holder-cost reversion when MVRV/NUPL signals extremes",
    data="Offline on-chain holder-cost and supply snapshots",
    features=("MVRV", "NUPL", "holder cost bases", "HODL waves"),
    category="onchain",
    documented=True,
    entry_exit="Enter on extreme unrealized-PnL reversion; exit at mean reversion or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Lagged on-chain feeds, regime shift, exchange-flow noise",
    data_exclusions="Stale or out-of-order on-chain snapshots",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-003",
    title="Funding-extreme mean reversion before settlement",
    mechanism="Funding-extreme mean reversion before settlement",
    data="Offline perp funding, OI, and liquidation-cascade history",
    features=("Perp funding", "OI/volume divergence", "liquidation cascades", "book depth"),
    category="derivatives_microstructure",
    documented=True,
    entry_exit="Enter against funding extreme; exit at funding normalization or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Funding regime change, crowded trade, venue inventory shock",
    data_exclusions="Missing or zero funding records, non-8h-aligned settlement",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-004",
    title="Liquidation-hunt fade after cascade exhaustion",
    mechanism="Liquidation-hunt fade after cascade exhaustion",
    data="Offline liquidation-cascade and book-depth history",
    features=("Liquidation cascades", "spoofing/layering flags", "bot crowding"),
    category="adversarial",
    documented=True,
    entry_exit="Fade exhaustion of a cascade; exit at reload or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Repeat cascade, spoof reversal, extraction by other bots",
    data_exclusions="Incomplete cascade records, synthetic-book artifacts",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-005",
    title="USD liquidity easing supports risk-on flows into BTC",
    mechanism="USD liquidity easing supports risk-on flows into BTC",
    data="Offline macro/liquidity and BTC spot history",
    features=("USD liquidity", "real yields", "DXY", "risk on/off"),
    category="macro_liquidity",
    documented=True,
    entry_exit="Enter on USD liquidity easing signal; exit at liquidity reversal or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Policy surprise, regime shift, correlation breakdown",
    data_exclusions="Stale macro prints, unverified CB balance-sheet data",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-006",
    title="Stablecoin mint/burn precedes spot pressure on BTC",
    mechanism="Stablecoin mint/burn precedes spot pressure on BTC",
    data="Offline stablecoin supply and BTC spot history",
    features=("Stablecoin mint/burn", "supply change", "exchange inflows"),
    category="flow_participation",
    documented=True,
    entry_exit="Enter on stablecoin mint/burn imbalance; exit at pressure exhaustion or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Exchange-wallet reclassification noise, bridged supply, delayed mint/burn reporting",
    data_exclusions="Unverified stablecoin reserves, opaque burn events",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
DEFAULT_HYPOTHESES.register(Hypothesis(
    hypothesis_id="H-007",
    title="Fear/greed exhaustion precedes contrarian moves",
    mechanism="Fear/greed exhaustion precedes contrarian moves",
    data="Offline sentiment and BTC price history",
    features=("Fear/greed", "social volume", "news shock", "sentiment extremes"),
    category="sentiment_attention",
    documented=True,
    entry_exit="Enter on sentiment exhaustion extreme; exit at reversion or stop",
    cost_edge="Move must exceed fees, spread, slippage, and funding",
    falsification="Negative net PnL or failure across embargoed walk-forward windows",
    failure_modes="Narrative persistence, sentiment manipulation, feed lag",
    data_exclusions="Spam social posts, unverified news sources, bot-driven sentiment",
    oos_gate="Minimum sample, cost-inclusive positive OOS evidence",
))
