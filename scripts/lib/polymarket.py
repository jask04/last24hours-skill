"""Polymarket prediction market search via Gamma API (free, no auth required).

Uses gamma-api.polymarket.com for event/market discovery.
No API key needed - public read-only API with generous rate limits (15K req/10s).
"""

import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import http, market_types
from .query_type import detect_query_type
from .relevance import LOW_SIGNAL_QUERY_TOKENS, token_overlap_relevance

GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"

# Pages to fetch per query (API returns 5 events per page, limit param is a no-op)
DEPTH_CONFIG = {
    "quick": 1,
    "default": 3,
    "deep": 4,
}

# Max events to return after merge + dedup + re-ranking
RESULT_CAP = {
    "quick": 5,
    "default": 15,
    "deep": 25,
}
_SPORTS_SLATE_ALIASES = {
    "nba": {"nba"},
    "nfl": {"nfl"},
    "mlb": {"mlb"},
    "nhl": {"nhl"},
}


def _matchup_side_tokens(text: str) -> List[set[str]]:
    text_lower = text.lower()
    separator = None
    for candidate in (" vs. ", " vs ", " at "):
        if candidate in text_lower:
            separator = candidate
            break
    if not separator:
        return []

    stop = {"the", "and", "at", "vs", "vs.", "of", "today", "tonight", "tomorrow"}
    sides = []
    for side in text_lower.split(separator, 1):
        tokens = {
            token
            for token in re.sub(r"[^\w\s]", " ", side).split()
            if len(token) > 2 and token not in stop
        }
        if tokens:
            sides.append(tokens)
    return sides if len(sides) == 2 else []


def _matchup_signature(text: str) -> Optional[str]:
    sides = _matchup_side_tokens(text)
    if len(sides) != 2:
        return None
    normalized = [" ".join(sorted(side)) for side in sides]
    normalized.sort()
    return " | ".join(normalized)


def _matchup_sides_match(left: str, right: str) -> bool:
    left_sides = _matchup_side_tokens(left)
    right_sides = _matchup_side_tokens(right)
    if len(left_sides) != 2 or len(right_sides) != 2:
        return False
    for candidate in right_sides:
        if not any(candidate & side for side in left_sides):
            return False
    return True


def _log(msg: str):
    """Log to stderr (only in TTY mode to avoid cluttering Claude Code output)."""
    if sys.stderr.isatty():
        sys.stderr.write(f"[PM] {msg}\n")
        sys.stderr.flush()


def _extract_core_subject(topic: str) -> str:
    """Extract core subject from topic string.

    Strips common prefixes like 'last 7 days', 'what are people saying about', etc.
    """
    topic = topic.strip()
    # Remove common leading phrases
    prefixes = [
        r"^last \d+ days?\s+",
        r"^what(?:'s| is| are) (?:people saying about|happening with|going on with)\s+",
        r"^how (?:is|are)\s+",
        r"^tell me about\s+",
        r"^research\s+",
    ]
    for pattern in prefixes:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE)
    return topic.strip()


def _detect_sports_league(topic: str) -> Optional[str]:
    topic_lower = topic.lower()
    for league, aliases in _SPORTS_SLATE_ALIASES.items():
        if any(alias in topic_lower for alias in aliases):
            return league
    return None


def _is_sports_slate_query(topic: str) -> bool:
    topic_lower = topic.lower()
    return bool(_detect_sports_league(topic) and any(term in topic_lower for term in ("games tonight", "games today", "tonight", "today", "slate")))


def _expand_queries(topic: str) -> List[str]:
    """Generate search queries to cast a wider net.

    Strategy:
    - Always include the core subject
    - Add ALL individual words as standalone searches (not just first)
    - Include the full topic if different from core
    - Cap at 6 queries, dedupe
    """
    core = _extract_core_subject(topic)
    queries = [core]
    league = _detect_sports_league(topic)
    if league and _is_sports_slate_query(topic):
        queries.insert(0, league.upper())

    # Add ALL individual words as separate queries
    words = core.split()
    if len(words) >= 2:
        for word in words:
            if len(word) > 1 and word.lower() not in LOW_SIGNAL_QUERY_TOKENS:
                queries.append(word)

    # Add the full topic if different from core
    if topic.lower().strip() != core.lower():
        queries.append(topic.strip())

    # Dedupe while preserving order, cap at 6
    seen = set()
    unique = []
    for q in queries:
        q_lower = q.lower().strip()
        if q_lower and q_lower not in seen:
            seen.add(q_lower)
            unique.append(q.strip())
    return unique[:6]


_GENERIC_TAGS = frozenset({"sports", "politics", "crypto", "science", "culture", "pop culture"})


def _event_has_tag(event: Dict[str, Any], values: set[str]) -> bool:
    tags = event.get("tags") or []
    labels = {
        (tag.get("label", "") if isinstance(tag, dict) else str(tag)).lower()
        for tag in tags
    }
    return bool(labels & values)


def _extract_domain_queries(topic: str, events: List[Dict]) -> List[str]:
    """Extract domain-indicator search terms from first-pass event tags.

    Uses structured tag metadata from Gamma API events to discover broader
    domain categories (e.g., 'NCAA CBB' from a Big 12 basketball event).
    Falls back to frequent title bigrams if no useful tags exist.
    """
    query_words = set(_extract_core_subject(topic).lower().split())

    # Collect tag labels from all first-pass events, count occurrences
    tag_counts: Dict[str, int] = {}
    for event in events:
        tags = event.get("tags") or []
        for tag in tags:
            label = tag.get("label", "") if isinstance(tag, dict) else str(tag)
            if not label:
                continue
            label_lower = label.lower()
            # Skip generic category tags and tags matching existing queries
            if label_lower in _GENERIC_TAGS:
                continue
            if label_lower in query_words:
                continue
            tag_counts[label] = tag_counts.get(label, 0) + 1

    # Sort by frequency, take top 2 that appear in 2+ events
    domain_queries = [
        label for label, count in sorted(tag_counts.items(), key=lambda x: -x[1])
        if count >= 2
    ][:2]

    return domain_queries


def _search_single_query(query: str, page: int = 1) -> Dict[str, Any]:
    """Run a single search query against Gamma API."""
    params = {
        "q": query,
        "page": str(page),
        "events_status": "active",
        "keep_closed_markets": "0",
    }
    url = f"{GAMMA_SEARCH_URL}?{urlencode(params)}"

    try:
        response = http.request("GET", url, timeout=15, retries=2)
        return response
    except http.HTTPError as e:
        _log(f"Search failed for '{query}' page {page}: {e}")
        return {"events": [], "error": str(e)}
    except Exception as e:
        _log(f"Search failed for '{query}' page {page}: {e}")
        return {"events": [], "error": str(e)}


def _run_queries_parallel(
    queries: List[str], pages: int, all_events: Dict, errors: List, start_idx: int = 0,
) -> None:
    """Run (query, page) combinations in parallel, merging into all_events."""
    with ThreadPoolExecutor(max_workers=min(8, len(queries) * pages)) as executor:
        futures = {}
        for i, q in enumerate(queries, start=start_idx):
            for p in range(1, pages + 1):
                future = executor.submit(_search_single_query, q, p)
                futures[future] = i

        for future in as_completed(futures):
            query_idx = futures[future]
            try:
                response = future.result(timeout=15)
                if response.get("error"):
                    errors.append(response["error"])

                events = response.get("events", [])
                for event in events:
                    event_id = event.get("id", "")
                    if not event_id:
                        continue
                    if event_id not in all_events:
                        all_events[event_id] = (event, query_idx)
                    elif query_idx < all_events[event_id][1]:
                        all_events[event_id] = (event, query_idx)
            except Exception as e:
                errors.append(str(e))


def search_polymarket(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search Polymarket via Gamma API with two-pass query expansion.

    Pass 1: Run expanded queries in parallel, merge and dedupe by event ID.
    Pass 2: Extract domain-indicator terms from first-pass titles, search those.

    Args:
        topic: Search topic
        from_date: Start date (YYYY-MM-DD) - used for activity filtering
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'events' list and optional 'error'.
    """
    pages = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    cap = RESULT_CAP.get(depth, RESULT_CAP["default"])
    queries = _expand_queries(topic)

    _log(f"Searching for '{topic}' with queries: {queries} (pages={pages})")

    # Pass 1: run expanded queries in parallel
    all_events: Dict[str, tuple] = {}
    errors: List[str] = []
    _run_queries_parallel(queries, pages, all_events, errors)

    # Pass 2: extract domain-indicator terms from first-pass titles and search
    first_pass_events = [ev for ev, _ in all_events.values()]
    domain_queries = _extract_domain_queries(topic, first_pass_events)
    # Filter out queries we already ran
    seen_queries = {q.lower() for q in queries}
    domain_queries = [dq for dq in domain_queries if dq.lower() not in seen_queries]

    if domain_queries:
        _log(f"Domain expansion queries: {domain_queries}")
        _run_queries_parallel(domain_queries, 1, all_events, errors, start_idx=len(queries))

    merged_events = [ev for ev, _ in sorted(all_events.values(), key=lambda x: x[1])]
    total_queries = len(queries) + len(domain_queries)
    _log(f"Found {len(merged_events)} unique events across {total_queries} queries")

    result = {"events": merged_events, "_cap": cap}
    if errors and not merged_events:
        result["error"] = "; ".join(errors[:2])
    return result


def _format_price_movement(market: Dict[str, Any]) -> Optional[str]:
    """Pick the most significant price change and format it.

    Returns string like 'down 11.7% this month' or None if no significant change.
    """
    changes = [
        (abs(market.get("oneDayPriceChange") or 0), market.get("oneDayPriceChange"), "today"),
        (abs(market.get("oneWeekPriceChange") or 0), market.get("oneWeekPriceChange"), "this week"),
        (abs(market.get("oneMonthPriceChange") or 0), market.get("oneMonthPriceChange"), "this month"),
    ]

    # Pick the largest absolute change
    changes.sort(key=lambda x: x[0], reverse=True)
    abs_change, raw_change, period = changes[0]

    # Skip if change is less than 1% (noise)
    if abs_change < 0.01:
        return None

    direction = "up" if raw_change > 0 else "down"
    pct = abs_change * 100
    return f"{direction} {pct:.1f}% {period}"


def _parse_outcome_prices(market: Dict[str, Any]) -> List[tuple]:
    """Parse outcomePrices JSON string into list of (outcome_name, price) tuples."""
    outcomes_raw = market.get("outcomes") or []
    prices_raw = market.get("outcomePrices")

    if not prices_raw:
        return []

    # Both outcomes and outcomePrices can be JSON-encoded strings
    try:
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw
    except (json.JSONDecodeError, TypeError):
        outcomes = []

    try:
        if isinstance(prices_raw, str):
            prices = json.loads(prices_raw)
        else:
            prices = prices_raw
    except (json.JSONDecodeError, TypeError):
        return []

    result = []
    for i, price in enumerate(prices):
        try:
            p = float(price)
        except (ValueError, TypeError):
            continue
        name = outcomes[i] if i < len(outcomes) else f"Outcome {i+1}"
        result.append((name, p))

    return result


_GENERIC_SYNTH_LABELS = frozenset({
    "there",
    "it",
    "this",
    "that",
    "the",
    "a",
    "an",
    "fed",
    "federal reserve",
})


def _shorten_question(question: str) -> str:
    """Extract a short display name from a market question.

    'Will Arizona win the 2026 NCAA Tournament?' -> 'Arizona'
    'Will Duke be a number 1 seed in the 2026 NCAA...' -> 'Duke'
    """
    q = question.strip().rstrip("?")
    # "Will there be..." markets are condition labels, not useful outcome
    # subjects. Falling back to the raw question creates labels like "there".
    if re.match(r"^Will\s+there\s+be\b", q, re.IGNORECASE):
        return ""
    # Common patterns: "Will X win/be/...", "X wins/loses..."
    m = re.match(r"^Will\s+(.+?)\s+(?:win|be|make|reach|have|lose|qualify|advance|strike|agree|pass|sign|get|become|remain|stay|leave|survive|next|decrease|increase|cut|hike|raise|lower|hit|exceed|reach)\b", q, re.IGNORECASE)
    if m:
        subject = _clean_short_question_subject(m.group(1))
        if subject:
            return subject
    m = re.match(r"^Will\s+(.+?)\s+", q, re.IGNORECASE)
    if m and len(m.group(1).split()) <= 4:
        subject = _clean_short_question_subject(m.group(1))
        if subject:
            return subject
    return ""


def _clean_short_question_subject(subject: str) -> str:
    words = subject.strip().split()
    while words and words[0].lower() in {"the", "a", "an"}:
        words.pop(0)
    cleaned = " ".join(words).strip()
    if not cleaned or cleaned.lower() in _GENERIC_SYNTH_LABELS:
        return ""
    return cleaned


def _use_synthetic_outcomes(outcomes: List[tuple]) -> bool:
    """Return whether question-derived labels are good enough to display."""
    if len(outcomes) < 2:
        return False
    labels = [name.strip().lower() for name, _ in outcomes if name.strip()]
    if len(set(labels)) < 2:
        return False
    if any(label in _GENERIC_SYNTH_LABELS for label in labels):
        return False
    return True


def _compute_text_similarity(topic: str, title: str, outcomes: List[str] = None) -> float:
    """Score how well the event title (or outcome names) match the search topic.

    Returns 0.0-1.0. Exact title phrase match gets 1.0. Otherwise we reuse the
    shared query-centric relevance scorer and take the best title/outcome match.
    """
    core = _extract_core_subject(topic).lower()
    title_lower = title.lower()
    if not core:
        return 0.5

    # Full substring match in title
    if core in title_lower:
        return 1.0

    query_type = detect_query_type(topic)
    title_score = token_overlap_relevance(core, title)
    best_score = title_score

    if outcomes:
        for outcome_name in outcomes:
            outcome_lower = outcome_name.lower()
            outcome_score = token_overlap_relevance(core, outcome_name)
            if _strong_phrase_match(core, outcome_lower):
                outcome_score = max(outcome_score, 0.92 if len(outcome_lower.split()) >= 2 else 0.88)
            if title_score < 0.3:
                outcome_cap = 0.55 if query_type == "prediction" else 0.24
                outcome_score = min(outcome_cap, outcome_score)
            else:
                outcome_score = max(title_score, 0.75 * title_score + 0.25 * outcome_score)
            best_score = max(best_score, outcome_score)

    return round(best_score, 2)


def _strong_phrase_match(core: str, candidate: str) -> bool:
    """Require real token matches, not accidental short substrings.

    This prevents binary outcomes like "No" from matching "nano" or similar
    short-string accidents.
    """
    candidate = " ".join(re.sub(r"[^\w\s]", " ", candidate.lower()).split())
    core = " ".join(re.sub(r"[^\w\s]", " ", core.lower()).split())
    if not candidate or not core:
        return False

    candidate_tokens = candidate.split()
    core_tokens = set(core.split())

    if len(candidate_tokens) >= 2:
        return candidate in core or core in candidate

    token = candidate_tokens[0]
    return len(token) > 2 and token in core_tokens


def _safe_float(val, default=0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(val or default)
    except (ValueError, TypeError):
        return default


def _safe_optional_float(val) -> Optional[float]:
    """Convert a market field to float while preserving missing/blank values."""
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _top_implied_probability(outcome_prices: List[tuple]) -> Optional[float]:
    prices = [price for _, price in outcome_prices if price is not None]
    if not prices:
        return None
    return max(prices)


def _market_signal_quality(
    probability: Optional[float],
    best_bid: Optional[float],
    best_ask: Optional[float],
    spread: Optional[float],
    movement_24h: Optional[float],
    volume_24h: Optional[float],
    liquidity: Optional[float],
) -> tuple[float, str]:
    volume_score = min(1.0, math.log1p(max(volume_24h or 0.0, 0.0)) / math.log1p(1_000_000))
    liquidity_score = min(1.0, math.log1p(max(liquidity or 0.0, 0.0)) / math.log1p(500_000))
    movement_score = min(1.0, abs(movement_24h or 0.0) / 20.0)
    spread_score = 0.25
    missing = []
    if spread is None:
        missing.append("spread unavailable")
    else:
        spread_score = max(0.0, min(1.0, 1.0 - (spread / 0.20)))
    if volume_24h is None:
        missing.append("24h volume unavailable")
    if liquidity is None:
        missing.append("liquidity unavailable")

    quality = (
        0.34 * volume_score +
        0.30 * liquidity_score +
        0.22 * spread_score +
        0.14 * movement_score
    )
    if probability is not None and (probability <= 0.01 or probability >= 0.99):
        if volume_score < 0.65 and movement_score < 0.25:
            quality *= 0.65
            missing.append("near-certain price can be stale")
    if best_bid is None and best_ask is None and spread is None:
        missing.append("orderbook unavailable")
    return round(max(0.0, min(1.0, quality)), 3), "; ".join(dict.fromkeys(missing))


def parse_polymarket_response(response: Dict[str, Any], topic: str = "") -> List[Dict[str, Any]]:
    """Parse Gamma API response into normalized item dicts.

    Each event becomes one item showing its title and top markets.

    Args:
        response: Raw Gamma API response
        topic: Original search topic (for relevance scoring)

    Returns:
        List of item dicts ready for normalization.
    """
    events = response.get("events", [])
    items = []
    league = _detect_sports_league(topic) if topic else None
    topic_matchup_signature = _matchup_signature(topic) if topic else None
    league_tag_map = {
        "nba": {"nba"},
        "nfl": {"nfl"},
        "mlb": {"mlb"},
        "nhl": {"nhl"},
    }

    for i, event in enumerate(events):
        event_id = event.get("id", "")
        title = event.get("title", "")
        slug = event.get("slug", "")
        sports_slate_query = _is_sports_slate_query(topic)

        # Filter: skip closed/resolved events
        if event.get("closed", False):
            continue
        if not event.get("active", True):
            continue

        # Get markets for this event
        markets = event.get("markets", [])
        if not markets:
            continue

        # Filter to active, open markets with liquidity (excludes resolved markets)
        active_markets = []
        for m in markets:
            if m.get("closed", False):
                continue
            if not m.get("active", True):
                continue
            # Must have liquidity (resolved markets have 0 or None)
            try:
                liq = float(m.get("liquidity", 0) or 0)
            except (ValueError, TypeError):
                liq = 0
            if liq > 0:
                active_markets.append(m)

        if not active_markets:
            continue

        # Sort markets by volume (most liquid first)
        def market_volume(m):
            try:
                return float(m.get("volume", 0) or 0)
            except (ValueError, TypeError):
                return 0
        active_markets.sort(key=market_volume, reverse=True)

        # Take top market for the event
        top_market = active_markets[0]

        # Collect outcome names from ALL active markets (not just top) for similarity scoring
        # Filter to outcomes with price > 1% to avoid noise
        # Also extract subjects from market questions for neg-risk events (outcomes are Yes/No)
        all_outcome_names = []
        for m in active_markets:
            for name, price in _parse_outcome_prices(m):
                if price > 0.01 and name not in all_outcome_names:
                    all_outcome_names.append(name)
            # For neg-risk binary markets (Yes/No outcomes), the team/entity name
            # lives in the question, e.g., "Will Arizona win the NCAA Tournament?"
            question = m.get("question", "")
            if question and question != title:
                all_outcome_names.append(question)

        # Parse outcome prices - for multi-market events with Yes/No binary
        # sub-markets, synthesize from market questions to show actual
        # team/entity probabilities instead of a single market's Yes/No
        outcome_prices = _parse_outcome_prices(top_market)
        synthetic_outcomes_used = False
        top_outcomes_are_binary = (
            len(outcome_prices) == 2
            and {n.lower() for n, _ in outcome_prices} == {"yes", "no"}
        )
        if top_outcomes_are_binary and len(active_markets) > 1:
            synth_outcomes = []
            for m in active_markets:
                q = m.get("question", "")
                if not q:
                    continue
                pairs = _parse_outcome_prices(m)
                yes_price = next((p for name, p in pairs if name.lower() == "yes"), None)
                if yes_price is not None and yes_price > 0.005:
                    synth_outcomes.append((q, yes_price))
            if synth_outcomes:
                synth_outcomes.sort(key=lambda x: x[1], reverse=True)
                shortened = [(_shorten_question(q), p) for q, p in synth_outcomes]
                cleaned_outcomes = [(name, p) for name, p in shortened if name]
                if _use_synthetic_outcomes(cleaned_outcomes):
                    outcome_prices = cleaned_outcomes
                    synthetic_outcomes_used = True

        # Format price movement
        price_movement = _format_price_movement(top_market)

        # Volume and liquidity - prefer event-level (more stable), fall back to market-level
        event_volume1mo = _safe_float(event.get("volume1mo"))
        event_volume1wk = _safe_float(event.get("volume1wk"))
        event_liquidity = _safe_float(event.get("liquidity"))
        event_competitive = _safe_float(event.get("competitive"))
        volume24hr = _safe_float(event.get("volume24hr")) or _safe_float(top_market.get("volume24hr"))
        liquidity = event_liquidity or _safe_float(top_market.get("liquidity"))
        implied_probability = _top_implied_probability(outcome_prices)
        best_bid = _safe_optional_float(top_market.get("bestBid") or top_market.get("best_bid") or top_market.get("bestBidPrice"))
        best_ask = _safe_optional_float(top_market.get("bestAsk") or top_market.get("best_ask") or top_market.get("bestAskPrice"))
        spread = _safe_optional_float(top_market.get("spread"))
        if len(outcome_prices) == 2 and best_bid is not None and best_ask is not None:
            top_label = max(outcome_prices, key=lambda pair: pair[1])[0]
            if str(top_label).strip().lower() == "no":
                best_bid, best_ask = max(0.0, 1.0 - best_ask), min(1.0, 1.0 - best_bid)
        if spread is None and best_bid is not None and best_ask is not None:
            spread = max(0.0, best_ask - best_bid)
        midpoint = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
        movement_24h = (
            (top_market.get("oneDayPriceChange") or 0) * 100
            if top_market.get("oneDayPriceChange") is not None
            else None
        )
        if synthetic_outcomes_used:
            # Multi-market events synthesize outcome labels from several
            # binary submarkets; a single submarket bid/ask/move would be
            # misleading for the synthesized top outcome.
            price_movement = None
            best_bid = None
            best_ask = None
            spread = None
            midpoint = None
            movement_24h = None
        signal_quality, signal_missing_reason = _market_signal_quality(
            implied_probability,
            best_bid,
            best_ask,
            spread,
            movement_24h,
            volume24hr,
            liquidity,
        )

        # Event URL
        url = f"https://polymarket.com/event/{slug}" if slug else f"https://polymarket.com/event/{event_id}"

        # Date: use updatedAt from event
        updated_at = event.get("updatedAt", "")
        date_str = None
        if updated_at:
            try:
                date_str = updated_at[:10]  # YYYY-MM-DD
            except (IndexError, TypeError):
                pass

        # End date for the market
        end_datetime = top_market.get("endDate")
        end_date = end_datetime
        if end_date:
            try:
                end_date = end_date[:10]
            except (IndexError, TypeError):
                end_date = None

        # Semantic relevance should dominate. Market quality should refine
        # relevant matches, not rescue unrelated high-liquidity events.
        text_score = _compute_text_similarity(topic, title, all_outcome_names) if topic else 0.5
        title_signature = _matchup_signature(title) or _matchup_signature(top_market.get("question", ""))
        if topic_matchup_signature:
            if title_signature == topic_matchup_signature or _matchup_sides_match(topic, title):
                text_score = max(text_score, 0.90)
            else:
                text_score = min(text_score, 0.22)
        if sports_slate_query:
            wanted_tags = league_tag_map.get(league, set())
            has_wanted_league = _event_has_tag(event, wanted_tags) if wanted_tags else False
            is_matchup = " vs. " in title.lower() or " vs " in title.lower() or " at " in title.lower()
            if has_wanted_league and is_matchup:
                text_score = max(text_score, 0.82)
            elif wanted_tags and not has_wanted_league:
                text_score = min(text_score, 0.12)
            elif _event_has_tag(event, {"awards", "mvp", "nba finals", "nba champion"}):
                text_score = min(text_score, 0.22)

        # Volume signal: log-scaled monthly volume (most stable signal)
        vol_raw = event_volume1mo or event_volume1wk or volume24hr
        vol_score = min(1.0, math.log1p(vol_raw) / 16)  # ~$9M = 1.0

        # Liquidity signal
        liq_score = min(1.0, math.log1p(liquidity) / 14)  # ~$1.2M = 1.0

        # Price movement: daily weighted more than monthly
        day_change = abs(top_market.get("oneDayPriceChange") or 0) * 3
        week_change = abs(top_market.get("oneWeekPriceChange") or 0) * 2
        month_change = abs(top_market.get("oneMonthPriceChange") or 0)
        max_change = max(day_change, week_change, month_change)
        movement_score = min(1.0, max_change * 5)  # 20% change = 1.0

        # Competitive bonus: markets near 50/50 are more interesting
        competitive_score = event_competitive

        market_quality = (
            0.50 * vol_score +
            0.25 * liq_score +
            0.15 * movement_score +
            0.10 * competitive_score
        )
        relevance = min(1.0, text_score * (0.75 + 0.25 * market_quality))
        if sports_slate_query and league_tag_map.get(league) and _event_has_tag(event, league_tag_map[league]) and (" vs. " in title.lower() or " vs " in title.lower() or " at " in title.lower()):
            relevance = max(relevance, 0.72 + 0.18 * market_quality)

        # Surface the topic-matching outcome to the front before truncating
        if topic and outcome_prices:
            core = _extract_core_subject(topic).lower()
            core_tokens = set(core.split())
            reordered = []
            rest = []
            for pair in outcome_prices:
                name_lower = pair[0].lower()
                # Match if full core is substring, or name is substring of core,
                # or any core token appears in the name (handles long question strings)
                if (core in name_lower or name_lower in core
                        or any(tok in name_lower for tok in core_tokens if len(tok) > 2)):
                    reordered.append(pair)
                else:
                    rest.append(pair)
            if reordered:
                outcome_prices = reordered + rest

        # Top 3 outcomes for multi-outcome markets
        top_outcomes = outcome_prices[:3]
        remaining = len(outcome_prices) - 3
        if remaining < 0:
            remaining = 0

        items.append({
            "event_id": event_id,
            "title": title,
            "question": top_market.get("question", title),
            "url": url,
            "outcome_prices": top_outcomes,
            "outcomes_remaining": remaining,
            "price_movement": price_movement,
            "price_movement_pct": movement_24h,
            "implied_probability": implied_probability,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "midpoint": midpoint,
            "movement_24h": movement_24h,
            "volume_24h": volume24hr,
            "market_signal_quality": signal_quality,
            "signal_timestamp": updated_at or None,
            "signal_missing_reason": signal_missing_reason,
            "market_type": market_types.classify_market(title, top_market.get("question", title), url),
            "volume24hr": volume24hr,
            "volume1mo": event_volume1mo,
            "liquidity": liquidity,
            "date": date_str,
            "end_date": end_date,
            "end_datetime": end_datetime,
            "relevance": round(relevance, 2),
            "why_relevant": f"Prediction market: {title[:60]}",
        })

    # Sort by relevance (quality-signal ranked) and apply cap
    items.sort(key=lambda x: x["relevance"], reverse=True)
    cap = response.get("_cap", len(items))
    return items[:cap]
