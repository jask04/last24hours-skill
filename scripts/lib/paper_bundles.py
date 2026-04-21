"""Paper-only multi-leg sports bundle synthesis."""

from __future__ import annotations

from itertools import combinations
import math
import re
from typing import Iterable, List, Optional, Tuple

from . import evidence_quality as eq, schema


_BUNDLE_INTENT_RE = re.compile(r"\b(paper\s+parlays?|parlay\s+ideas?|parlays?|multi[-\s]?leg|paper\s+bundles?|bundles?)\b", re.I)


def wants_paper_bundles(topic: str) -> bool:
    return bool(_BUNDLE_INTENT_RE.search(topic or ""))


def display_topic(topic: str) -> str:
    """Return paper-safe topic text for user-facing bundle output."""
    text = topic or ""
    text = re.sub(r"\bpaper\s+parlays?\b", "paper bundles", text, flags=re.I)
    text = re.sub(r"\bparlay\s+ideas?\b", "bundle ideas", text, flags=re.I)
    text = re.sub(r"\bparlays?\b", "bundles", text, flags=re.I)
    text = re.sub(r"\bmulti[-\s]?leg\b(?!\s+watchlist)", "multi-leg watchlist", text, flags=re.I)
    return text


def _prob(value) -> Optional[float]:
    if value is None:
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if probability > 1:
        probability /= 100.0
    if probability < 0 or probability > 1:
        return None
    return probability


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split())


def _team_tokens(item: schema.MarketWatchItem) -> List[str]:
    tokens = _tokens(f"{item.title} {item.question} {item.outcome_label}")
    return sorted(tokens & eq.NBA_TEAM_TOKENS)


def _game_key(item: schema.MarketWatchItem) -> str:
    teams = _team_tokens(item)
    if len(teams) >= 2:
        return "|".join(sorted(set(teams)))
    text = re.sub(r"\s+", " ", f"{item.title} {item.question}".lower()).strip()
    return re.sub(r"\W+", "-", text)[:80]


def _is_final_context(context: str) -> bool:
    lowered = (context or "").lower()
    return "final" in lowered or "postponed" in lowered or "canceled" in lowered or "cancelled" in lowered


def _is_live_context(context: str) -> bool:
    lowered = (context or "").lower()
    if _is_final_context(context):
        return False
    return any(term in lowered for term in ("period ", "quarter", "halftime", "overtime", " inning"))


def _is_scheduled_context(context: str) -> bool:
    lowered = (context or "").lower()
    if _is_final_context(context) or _is_live_context(context):
        return False
    return "scheduled" in lowered or "start " in lowered


def _eligible_leg(item: schema.MarketWatchItem) -> Tuple[Optional[schema.BundleLeg], str]:
    if item.market_type != "game_outcome":
        return None, "non_game_outcome"
    if not item.live_game_context:
        return None, "missing_espn_context"
    if item.live_match_confidence is None or item.live_match_confidence < 0.70:
        return None, "weak_espn_match"
    text = f"{item.title} {item.question}".lower()
    if any(term in text for term in ("series", "total games", "player", "points o/u", "assists o/u")):
        return None, "not_direct_game_market"
    probability = _prob(item.probability or item.implied_probability)
    if probability is None:
        return None, "missing_probability"
    if not (0.35 <= probability <= 0.80):
        return None, "extreme_probability"
    if (item.liquidity or 0) <= 0:
        return None, "no_liquidity"
    if item.spread is not None and item.spread > 0.15:
        return None, "wide_spread"
    if _is_final_context(item.live_game_context):
        return None, "game_final"
    if not _is_scheduled_context(item.live_game_context):
        return None, "game_not_scheduled"
    teams = _team_tokens(item)
    if len(teams) < 2:
        return None, "missing_team_match"
    rationale = "direct scheduled NBA game-outcome market with usable depth and non-extreme probability"
    if item.live_game_context:
        rationale += "; ESPN context attached"
    return schema.BundleLeg(
        id=item.id,
        title=item.title or item.question,
        venue=item.venue,
        url=item.url,
        outcome_label=item.outcome_label,
        probability=round(probability, 4),
        source_item_id=item.source_item_id,
        market_type=item.market_type,
        game_key=_game_key(item),
        team_tokens=teams,
        live_game_context=item.live_game_context,
        rank_score=item.rank_score,
        rationale=rationale,
    ), ""


def _compatible(legs: Iterable[schema.BundleLeg]) -> bool:
    seen_games: set[str] = set()
    seen_teams: set[str] = set()
    for leg in legs:
        if leg.game_key in seen_games:
            return False
        teams = set(leg.team_tokens)
        if seen_teams & teams:
            return False
        seen_games.add(leg.game_key)
        seen_teams |= teams
    return True


def _combined_probability(legs: List[schema.BundleLeg]) -> float:
    return round(math.prod(leg.probability for leg in legs), 4)


def _confidence(legs: List[schema.BundleLeg]) -> str:
    avg_rank = sum(leg.rank_score for leg in legs) / max(1, len(legs))
    if avg_rank >= 60 and all(leg.probability <= 0.72 for leg in legs):
        return "moderate"
    if avg_rank >= 45:
        return "low-moderate"
    return "low"


def _bundle_score(legs: List[schema.BundleLeg]) -> float:
    avg_rank = sum(leg.rank_score for leg in legs) / max(1, len(legs))
    balance = sum(1.0 - abs(leg.probability - 0.55) for leg in legs) / max(1, len(legs))
    return avg_rank + 20 * balance - 10 * max(0, len(legs) - 2)


def synthesize_paper_bundles(report: schema.Report, limit: int = 3) -> Tuple[List[schema.PaperBundle], str]:
    """Create paper-only multi-leg bundles from watchlist game-outcome markets."""
    if not wants_paper_bundles(report.topic):
        return [], ""
    if "nba" not in report.topic.lower():
        return [], "paper bundle v1 only supports NBA prompts."
    if not report.market_watchlist:
        return [], "no watchlist markets cleared the filters."

    legs = []
    reject_reasons = {}
    for item in report.market_watchlist:
        leg, reason = _eligible_leg(item)
        if leg:
            legs.append(leg)
        elif reason:
            reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
    if reject_reasons:
        debug = report.evidence_fusion_stats.setdefault("debug_counters", {})
        debug["bundle_leg_rejection_count"] = sum(reject_reasons.values())
        report.evidence_fusion_stats["bundle_leg_rejection_counts"] = dict(sorted(reject_reasons.items()))

    if len(legs) < 2:
        if reject_reasons.get("missing_probability"):
            return [], "too few direct NBA game markets with usable probabilities."
        if reject_reasons.get("no_liquidity"):
            return [], "too few direct NBA game markets with positive liquidity."
        if reject_reasons.get("game_final"):
            return [], "too few eligible games remain because ESPN context marks them final."
        if reject_reasons.get("game_not_scheduled"):
            return [], "too few eligible games remain because bundle legs must be scheduled and not already live."
        if reject_reasons.get("missing_espn_context") or reject_reasons.get("weak_espn_match"):
            return [], "too few direct NBA game markets had trusted ESPN matchup context."
        return [], "too few direct NBA game-outcome markets qualified for a paper bundle."

    candidates: List[List[schema.BundleLeg]] = []
    for size in (2, 3):
        if size == 3 and len(legs) < 5:
            continue
        for combo in combinations(legs, size):
            combo_list = list(combo)
            if _compatible(combo_list):
                candidates.append(combo_list)

    if not candidates:
        return [], "direct game markets qualified individually, but same-game or same-team overlap blocked bundle construction."

    candidates.sort(key=_bundle_score, reverse=True)
    bundles = []
    seen_keys = set()
    for combo in candidates:
        key = tuple(sorted(leg.source_item_id or leg.id for leg in combo))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        bundle_id = f"PB{len(bundles) + 1}"
        legs_text = " + ".join(f"{leg.outcome_label or 'Top outcome'} ({leg.title})" for leg in combo)
        bundles.append(schema.PaperBundle(
            id=bundle_id,
            title=f"Paper Bundle {len(bundles) + 1}: {legs_text}",
            legs=combo,
            combined_probability_independence=_combined_probability(combo),
            confidence_bucket=_confidence(combo),
            correlation_warning="Rough independence baseline only; same-league NBA legs can share injury, lineup, pace, market-flow, and playoff-context risk.",
            rationale="Each leg is a direct NBA game-outcome market with usable liquidity and a non-extreme listed probability.",
            fragility="A late injury report, lineup change, live score swing, or sharp market repricing can break the bundle.",
            paper_only=True,
        ))
        if len(bundles) >= limit:
            break

    return bundles, ""
