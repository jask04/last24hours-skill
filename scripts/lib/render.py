"""Output rendering for last24hours skill."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from . import evidence_quality as eq, market_types, query_type as qt, schema

OUTPUT_DIR = Path.home() / ".local" / "share" / "last24hours" / "out"


def _xref_tag(item) -> str:
    """Return ' [also on: Reddit, HN]' string if item has cross_refs, else ''."""
    refs = getattr(item, 'cross_refs', None)
    if not refs:
        return ""
    source_names = set()
    for ref_id in refs:
        if ref_id.startswith('R'):
            source_names.add('Reddit')
        elif ref_id.startswith('X'):
            source_names.add('X')
        elif ref_id.startswith('YT'):
            source_names.add('YouTube')
        elif ref_id.startswith('TK'):
            source_names.add('TikTok')
        elif ref_id.startswith('IG'):
            source_names.add('Instagram')
        elif ref_id.startswith('HN'):
            source_names.add('HN')
        elif ref_id.startswith('BS'):
            source_names.add('Bluesky')
        elif ref_id.startswith('TS'):
            source_names.add('Truth Social')
        elif ref_id.startswith('PM'):
            source_names.add('Polymarket')
        elif ref_id.startswith('KA'):
            source_names.add('Kalshi')
        elif ref_id.startswith('WX'):
            source_names.add('Weather')
        elif ref_id.startswith('W'):
            source_names.add('Web')
    if source_names:
        return f" [also on: {', '.join(sorted(source_names))}]"
    return ""


def ensure_output_dir():
    """Ensure output directory exists. Supports env override and sandbox fallback."""
    global OUTPUT_DIR
    env_dir = os.environ.get("LAST24HOURS_OUTPUT_DIR")
    if env_dir:
        OUTPUT_DIR = Path(env_dir)

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        OUTPUT_DIR = Path(tempfile.gettempdir()) / "last24hours" / "out"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except PermissionError:
        global OUTPUT_DIR
        OUTPUT_DIR = Path(tempfile.gettempdir()) / "last24hours" / "out"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / path.name, 'w', encoding='utf-8') as f:
            f.write(content)


def _write_json(path: Path, payload) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
    except PermissionError:
        global OUTPUT_DIR
        OUTPUT_DIR = Path(tempfile.gettempdir()) / "last24hours" / "out"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / path.name, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)


def _assess_data_freshness(report: schema.Report) -> dict:
    """Assess how much data is actually from the last 24 hours."""
    reddit_recent = sum(1 for r in report.reddit if r.date and r.date >= report.range_from)
    x_recent = sum(1 for x in report.x if x.date and x.date >= report.range_from)
    web_recent = sum(1 for w in report.web if w.date and w.date >= report.range_from)
    weather_recent = sum(1 for w in report.weather if w.date and w.date >= report.range_from)
    hn_recent = sum(1 for h in report.hackernews if h.date and h.date >= report.range_from)
    bsky_recent = sum(1 for b in report.bluesky if b.date and b.date >= report.range_from)
    ts_recent = sum(1 for ts in report.truthsocial if ts.date and ts.date >= report.range_from)
    pm_recent = sum(1 for p in report.polymarket if p.date and p.date >= report.range_from)
    ka_recent = sum(1 for k in report.kalshi if k.date and k.date >= report.range_from)

    tiktok_recent = sum(1 for t in report.tiktok if t.date and t.date >= report.range_from)
    ig_recent = sum(1 for ig in report.instagram if ig.date and ig.date >= report.range_from)

    total_recent = reddit_recent + x_recent + web_recent + weather_recent + hn_recent + bsky_recent + ts_recent + pm_recent + ka_recent + tiktok_recent + ig_recent
    total_items = len(report.reddit) + len(report.x) + len(report.web) + len(report.weather) + len(report.hackernews) + len(report.bluesky) + len(report.truthsocial) + len(report.polymarket) + len(report.kalshi) + len(report.tiktok) + len(report.instagram)

    return {
        "reddit_recent": reddit_recent,
        "x_recent": x_recent,
        "web_recent": web_recent,
        "weather_recent": weather_recent,
        "total_recent": total_recent,
        "total_items": total_items,
        "is_sparse": total_recent < 5,
        "mostly_evergreen": total_items > 0 and total_recent < total_items * 0.3,
    }


def _is_nba_slate_topic(topic: str) -> bool:
    topic_lower = topic.lower()
    return "nba" in topic_lower and any(term in topic_lower for term in (
        "games today", "games tonight", "games tomorrow", "tomorrows nba games",
        "tomorrow's nba games", "todays nba games", "today's nba games", "nba slate",
    ))


def _matchup_side_tokens(text: str) -> list[set[str]]:
    separator = None
    text_lower = text.lower()
    for candidate in (" vs. ", " vs ", " at "):
        if candidate in text_lower:
            separator = candidate
            break
    if not separator:
        return []
    stop = {"the", "and", "at", "vs", "vs.", "of"}
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


def _prediction_domain(topic: str) -> Optional[str]:
    topic_lower = (topic or "").lower()
    if _is_nba_slate_topic(topic) or _matchup_signature(topic):
        return "sports"
    if eq.is_weather_query(topic_lower):
        return "weather"
    if eq.is_macro_query(topic_lower):
        return "macro"
    return None


def _market_forecast_line(item: schema.PolymarketItem) -> Optional[tuple[str, str, str]]:
    if not item.outcome_prices:
        return None
    ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
    forecast_line, favorite_name = _market_call_from_item(item)
    market_parts = []
    for name, price in ordered[:2]:
        clean_name = _clean_outcome_name(name) or ("Yes" if price == ordered[0][1] else "Other")
        market_parts.append(f"{clean_name}: {price * 100:.0f}%")
    market_view = " | ".join(market_parts)
    if item.price_movement:
        market_view += f" ({item.price_movement})"
    uncertainty = "Tight market" if len(ordered) > 1 and abs((ordered[0][1] - ordered[1][1]) * 100) < 8 else "Moderate edge"
    return (forecast_line, market_view, uncertainty)


def _forecast_change_line(item: schema.PolymarketItem) -> str:
    ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True) if item.outcome_prices else []
    gap = abs((ordered[0][1] - ordered[1][1]) * 100) if len(ordered) > 1 else 0.0
    if gap < 8:
        return "What changes the number: one lineup or injury update could flip this."
    if item.price_movement_pct is not None and abs(item.price_movement_pct) >= 8:
        return "What changes the number: the market has already moved sharply; another major injury/rest report would matter most."
    return "What changes the number: starting lineups, injury/rest news, and late market moves near tipoff."


def _evidence_snippet(report: schema.Report, sides: list[set[str]]) -> Optional[str]:
    candidates = []
    driver_terms = {
        "injury", "injuries", "out", "ruled", "rest", "resting", "lineup",
        "starting", "starter", "bench", "doubtful", "questionable", "available",
        "inactive", "tank", "playoff", "seed", "odds", "moneyline",
    }
    low_signal_terms = {
        "ticket", "tickets", "dm", "interested", "selling", "sale",
        "placed", "bet", "bettorbot", "asking", "section", "row",
    }

    for item in report.x[:12]:
        text = getattr(item, "text", "")
        tokens = set(re.sub(r"[^\w\s]", " ", text.lower()).split())
        if all(side & tokens for side in sides):
            if "bettorbot" in tokens or {"ticket", "tickets", "selling", "sale", "resale"} & tokens:
                continue
            if low_signal_terms & tokens and not driver_terms & tokens:
                continue
            bonus = 12 if driver_terms & tokens else 0
            penalty = 20 if (low_signal_terms & tokens and not driver_terms & tokens) else 0
            candidates.append((getattr(item, "score", 0) + bonus - penalty, text))

    for item in report.reddit[:8]:
        text = f"{getattr(item, 'title', '')} {getattr(item, 'subreddit', '')}"
        tokens = set(re.sub(r"[^\w\s]", " ", text.lower()).split())
        if all(side & tokens for side in sides):
            if "bettorbot" in tokens or {"ticket", "tickets", "selling", "sale", "resale"} & tokens:
                continue
            if low_signal_terms & tokens and not driver_terms & tokens:
                continue
            bonus = 6 if driver_terms & tokens else 0
            candidates.append((getattr(item, "score", 0) + bonus, getattr(item, "title", "")))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    snippet = candidates[0][1].strip().replace("\n", " ")
    return snippet[:160] + ("..." if len(snippet) > 160 else "")


def _short_text(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _matching_kalshi_item(report: schema.Report, signature: str) -> Optional[schema.KalshiItem]:
    for item in report.kalshi:
        candidate_sig = _matchup_signature(item.title or item.question)
        if candidate_sig == signature and item.current_probability is not None:
            return item
    return None


def _market_divergence_line(report: schema.Report, signature: str) -> Optional[str]:
    item = _matching_kalshi_item(report, signature)
    if not item:
        return None
    return f"Kalshi view: YES {item.current_probability * 100:.0f}%"


def _market_divergence_detail(report: schema.Report, poly_item: schema.PolymarketItem) -> Optional[str]:
    signature = _matchup_signature(poly_item.title or poly_item.question)
    if not signature:
        return None
    kalshi_item = _matching_kalshi_item(report, signature)
    if not kalshi_item or kalshi_item.current_probability is None or not poly_item.outcome_prices:
        return None

    ordered = sorted(poly_item.outcome_prices, key=lambda pair: pair[1], reverse=True)
    favorite_name, favorite_price = ordered[0]
    gap = abs((favorite_price - kalshi_item.current_probability) * 100)
    if gap < 4:
        return f"Polymarket and Kalshi are broadly aligned on {favorite_name}."
    richer = "Polymarket" if favorite_price > kalshi_item.current_probability else "Kalshi"
    return f"Polymarket/Kalshi spread: about {gap:.0f} pts; {richer} is pricing the favorite higher."


def _format_probability_range(item: schema.ForecastItem) -> str:
    if item.forecast_range_low is not None and item.forecast_range_high is not None:
        low = item.forecast_range_low * 100
        high = item.forecast_range_high * 100
        if abs(high - low) < 1.0:
            return f"{high:.0f}%"
        return f"{low:.0f}-{high:.0f}%"
    if item.forecast_probability is not None:
        return f"{item.forecast_probability * 100:.0f}%"
    return "unknown"


def _forecast_display_label(item: schema.ForecastItem) -> str:
    label = item.favorite_label or "Yes"
    if item.anchor_source == "model_implied" and label.lower() in {"yes", "no"} and _matchup_signature(item.title):
        return "Model-implied lean"
    return label


def _anchor_label(item: schema.ForecastItem) -> str:
    labels = {
        "polymarket": "Polymarket-led",
        "kalshi": "Kalshi-led",
        "blended": "Blended market anchor",
        "weather_api": "NWS-led",
        "model_implied": "Model-implied",
    }
    return labels.get(item.anchor_source, item.anchor_source)


def _render_forecast_item(item: schema.ForecastItem) -> list[str]:
    lines = [f"**{item.title}**"]
    probability_range = _format_probability_range(item)
    call = _forecast_display_label(item)
    lines.append(f"Forecast: {call} {probability_range}")
    market_view = item.market_view or "No clean market view available."
    lines.append(f"Market view: {market_view} [{_anchor_label(item)}]")
    if item.why_line:
        lines.append(f"Why this is the current line: {item.why_line}")
    lines.append(f"Confidence / uncertainty: {item.confidence_level} confidence. {item.uncertainty}")
    if item.upside_catalysts or item.downside_catalysts:
        up = "; ".join(item.upside_catalysts[:2]) if item.upside_catalysts else "No clear upside catalysts."
        down = "; ".join(item.downside_catalysts[:2]) if item.downside_catalysts else "No clear downside catalysts."
        lines.append(f"What changes the number: Up: {up} Down: {down}")
    return lines


def _format_watch_probability(item: schema.MarketWatchItem) -> str:
    if item.probability is None:
        return "probability unavailable"
    return f"{item.outcome_label or 'Top outcome'} {item.probability * 100:.0f}%"


def _format_market_type(market_type: str) -> str:
    labels = {
        "game_outcome": "Game outcome",
        "player_prop": "Player prop",
        "team_prop": "Team prop",
        "futures": "Futures",
        "threshold": "Threshold",
        "macro_binary": "Macro binary",
        "weather_binary": "Weather binary",
    }
    return labels.get(market_type or "unknown", "Market")


def _render_market_watchlist_summary(report: schema.Report) -> list[str]:
    if qt.detect_query_type(report.topic) != "market_watchlist":
        return []

    lines = ["### Market Picks To Watch", ""]
    lines.append("*Informational market-monitoring output, not trade execution or allocation advice.*")
    lines.append("")
    if not report.market_watchlist:
        lines.append("No high-quality market picks found.")
        lines.append("Filters: needed topic-relevant Polymarket/Kalshi candidates with enough market depth, movement, catalyst evidence, or cross-market signal.")
        lines.append("If the prompt is broad, narrow it by domain, league, asset, or macro theme for a cleaner scan.")
        lines.append("")
        return lines

    for item in report.market_watchlist:
        lines.append(f"**{item.id}. {item.title or item.question}**")
        lines.append(f"Pick: {item.venue} {_format_market_type(item.market_type)} - {_format_watch_probability(item)}")
        lines.append(f"Why it ranks: {item.why_ranks} (rank score {item.rank_score}/100).")
        lines.append(f"Market signal: {item.market_signal}")
        catalyst = item.catalyst_summary or "Catalyst context is thin; ranking is mostly market-signal driven."
        if item.evidence_refs:
            catalyst += f" Evidence refs: {', '.join(item.evidence_refs[:3])}."
        lines.append(f"Catalyst / evidence: {catalyst}")
        risk = item.risk or "Fresh news or market repricing could change the ranking."
        if item.cross_market_note:
            risk += f" {item.cross_market_note}"
        lines.append(f"Risk / what would change it: {risk}")
        if item.end_date:
            lines.append(f"Expiration: {item.end_date}")
        if item.url:
            lines.append(item.url)
        lines.append("")
    return lines


def _used_market_ids(report: schema.Report) -> tuple[set[str], set[str]]:
    poly_ids = {item.polymarket_market_id for item in report.forecasts if item.polymarket_market_id}
    kalshi_ids = {item.kalshi_market_id for item in report.forecasts if item.kalshi_market_id}
    poly_ids |= {item.source_item_id for item in report.market_watchlist if item.source_item_id.startswith("PM")}
    kalshi_ids |= {item.source_item_id for item in report.market_watchlist if item.source_item_id.startswith("KA")}
    return poly_ids, kalshi_ids


def _top_prediction_evidence(report: schema.Report, limit: int = 3) -> list[str]:
    driver_terms = {
        "injury", "injuries", "out", "ruled", "questionable", "doubtful", "available",
        "rest", "resting", "lineup", "lineups", "starter", "starters", "bench",
        "playoff", "playoffs", "seed", "seeding", "elimination", "clinch", "clinched",
        "tank", "tanking", "odds", "spread", "moneyline", "probability", "forecast",
        "rain", "snow", "storm", "wind", "temperature", "watch", "warning",
    }
    items = []
    topic_tokens = set(re.sub(r"[^\w\s-]", " ", report.topic.lower()).split())
    stop = {"will", "the", "a", "an", "to", "by", "of", "in", "on", "for", "tomorrow", "today", "tonight"}
    weather_query = any(term in report.topic.lower() for term in ("weather", "rain", "snow", "storm", "wind", "temperature"))
    strict_weather_terms = {"forecast", "weather", "radar", "showers", "precip", "precipitation", "storm", "warning", "watch", "temperature", "wind"}

    for item in report.x[:10]:
        text = getattr(item, "text", "")
        tokens = set(re.sub(r"[^\w\s-]", " ", text.lower()).split())
        overlap = (topic_tokens - stop) & tokens
        if len(overlap) < 1 and not driver_terms & tokens:
            continue
        if weather_query and not (strict_weather_terms & tokens):
            continue
        if {"ticket", "tickets", "selling", "sale", "resale", "bettorbot"} & tokens and not driver_terms & tokens:
            continue
        bonus = 8 if driver_terms & tokens else 0
        items.append((getattr(item, "score", 0) + bonus, _short_text(text)))

    for item in report.reddit[:8]:
        text = getattr(item, "title", "")
        tokens = set(re.sub(r"[^\w\s-]", " ", text.lower()).split())
        overlap = (topic_tokens - stop) & tokens
        if len(overlap) < 1 and not driver_terms & tokens:
            continue
        if weather_query and not (strict_weather_terms & tokens):
            continue
        bonus = 6 if driver_terms & tokens else 0
        items.append((getattr(item, "score", 0) + bonus, _short_text(text)))

    for item in report.web[:6]:
        text = f"{getattr(item, 'title', '')} {getattr(item, 'snippet', '')}"
        tokens = set(re.sub(r"[^\w\s-]", " ", text.lower()).split())
        overlap = (topic_tokens - stop) & tokens
        if len(overlap) < 1 and not driver_terms & tokens:
            continue
        if weather_query and not (strict_weather_terms & tokens):
            continue
        bonus = 5 if driver_terms & tokens else 0
        items.append((getattr(item, "score", 0) + bonus, _short_text(getattr(item, "title", "") or getattr(item, "snippet", ""))))

    items.sort(key=lambda pair: pair[0], reverse=True)
    seen = set()
    results = []
    for _, text in items:
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def _prediction_confidence(report: schema.Report, has_markets: bool) -> str:
    evidence_count = len(report.x[:5]) + len(report.reddit[:5]) + len(report.web[:5])
    if has_markets and report.polymarket and report.kalshi:
        return "Moderate confidence; market-backed with cross-checking from both venues."
    if has_markets and evidence_count >= 4:
        return "Moderate confidence; market-backed, but still sensitive to late information."
    if has_markets:
        return "Moderate-low confidence; market-backed, but the supporting evidence is thin."
    if evidence_count >= 5:
        return "Low confidence; model-implied without a live market anchor."
    return "Low confidence; no clean market and limited recent evidence."


def _prediction_change_line(report: schema.Report, poly_item: Optional[schema.PolymarketItem] = None) -> str:
    topic = report.topic.lower()
    if any(term in topic for term in ("rain", "snow", "storm", "weather", "temperature", "wind")):
        return "What changes the number: updated radar/model runs, watches or warnings, and any shift in storm track or timing."
    if any(term in topic for term in ("election", "poll", "approval", "rate cut", "inflation", "cpi", "fed")):
        return "What changes the number: fresh polling/data releases, official statements, and any sharp market repricing."
    if poly_item:
        return _forecast_change_line(poly_item)
    return "What changes the number: fresh high-signal reporting, new market prices, and any contradicting source update."


def _clean_outcome_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "")).strip()
    if not cleaned:
        return ""
    generic = {"the", "there", "yes", "no", "1", "2", "3", "4", "5"}
    if cleaned.lower() in generic:
        return ""
    return cleaned


def _market_call_from_item(item: schema.PolymarketItem) -> tuple[str, str]:
    ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
    favorite_name, favorite_price = ordered[0]
    favorite_name = _clean_outcome_name(favorite_name)
    if favorite_name:
        return f"{favorite_name} {favorite_price * 100:.0f}%", favorite_name
    return f"Implied yes {favorite_price * 100:.0f}%", "yes"


def _best_polymarket_for_topic(report: schema.Report) -> Optional[schema.PolymarketItem]:
    if not report.polymarket:
        return None

    topic_signature = _matchup_signature(report.topic)
    if topic_signature:
        matching = [
            item for item in report.polymarket
            if _matchup_signature(item.title or item.question) == topic_signature
        ]
        if matching:
            return max(matching, key=lambda item: item.score)

    topic_tokens = {
        token for token in re.sub(r"[^\w\s]", " ", report.topic.lower()).split()
        if len(token) > 2 and token not in {"will", "the", "for", "and", "tomorrow", "today", "tonight"}
    }
    ranked = []
    for item in report.polymarket:
        market_text = f"{item.title} {item.question}".lower()
        overlap = len(topic_tokens & set(re.sub(r"[^\w\s]", " ", market_text).split()))
        ranked.append((overlap, item.score, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return ranked[0][2] if ranked and ranked[0][0] > 0 else report.polymarket[0]


def _render_prediction_summary(report: schema.Report) -> list[str]:
    if qt.detect_query_type(report.topic) != "prediction":
        return []

    if not report.forecasts:
        if _is_nba_slate_topic(report.topic):
            return [
                "### Forecast",
                "",
                f"**{report.topic}**",
                "Forecast: No direct slate forecast available",
                "Market view: No direct NBA game Polymarket or Kalshi market cleared league filtering.",
                "Why this is the current line: No scheduled-game market or high-signal team-specific driver surfaced in the current quick run.",
                "Confidence / uncertainty: low confidence. Treat this as a source-availability result, not a game forecast.",
                "What changes the number: Up: Direct team-vs-team markets or official slate data appears Down: Only futures/awards or cross-league markets remain available",
                "",
            ]
        return []
    if len(report.forecasts) > 1:
        lines = ["### Slate Forecast Board", ""]
        for forecast in report.forecasts:
            lines.extend(_render_forecast_item(forecast))
            lines.append("")
        return lines
    lines = ["### Forecast", ""]
    lines.extend(_render_forecast_item(report.forecasts[0]))
    lines.append("")
    return lines


def _compact_sports_items(items: list, source: str, report: schema.Report, limit: int) -> list:
    if qt.detect_query_type(report.topic) == "market_watchlist":
        return []
    if qt.detect_query_type(report.topic) != "prediction" or not _is_nba_slate_topic(report.topic) and not _matchup_signature(report.topic):
        return items[:limit]

    driver_terms = {
        "injury", "injuries", "ruled", "questionable", "doubtful", "probable",
        "available", "inactive", "rest", "resting", "lineup", "lineups", "starter",
        "starters", "minutes", "restriction", "restricted", "playoff", "playoffs",
        "seed", "seeding", "elimination", "clinch", "clinched", "tank", "tanking",
    }
    weak_market_terms = {"odds", "line", "spread", "moneyline", "sportsbook", "fanduel", "draftkings"}
    low_signal = {
        "ticket", "tickets", "selling", "sale", "resale", "section", "row", "seat",
        "bettorbot", "parlay", "pick", "picks", "lock", "tail", "sprinkle",
    }
    filtered = []
    fallback = []
    for item in items:
        text = getattr(item, "text", "") or getattr(item, "title", "") or ""
        tokens = set(re.sub(r"[^\w\s-]", " ", text.lower()).split())
        if "check" in tokens and "out" in tokens:
            tokens.discard("out")
        if source == "reddit":
            tokens |= set(re.sub(r"[^\w\s-]", " ", getattr(item, "subreddit", "").lower()).split())
        if _is_nba_slate_topic(report.topic) and not ((eq.NBA_TEAM_TOKENS & tokens) or "nba" in tokens):
            continue
        if len(tokens & {"lakers", "warriors", "celtics", "knicks", "heat", "raptors", "bulls", "wizards", "rockets", "sixers", "pacers", "nets", "nuggets", "grizzlies"}) >= 4:
            continue
        if low_signal & tokens and not driver_terms & tokens:
            continue
        if weak_market_terms & tokens and not driver_terms & tokens:
            fallback.append(item)
            continue
        if driver_terms & tokens:
            filtered.append(item)
        else:
            fallback.append(item)
    if filtered:
        return filtered[:limit]
    return []


def _is_nba_market_item(item) -> bool:
    text = f"{getattr(item, 'title', '')} {getattr(item, 'question', '')} {getattr(item, 'url', '')}"
    item_type = getattr(item, "market_type", "unknown")
    if item_type == "unknown":
        item_type = market_types.classify_market(
            getattr(item, "title", ""),
            getattr(item, "question", ""),
            getattr(item, "url", ""),
        )
    return eq.is_nba_market_text(text) and item_type == "game_outcome"


def _compact_weather_macro_items(items: list, source: str, report: schema.Report, limit: int) -> list:
    if qt.detect_query_type(report.topic) != "prediction":
        return items[:limit]
    domain = _prediction_domain(report.topic)
    if domain not in {"weather", "macro"}:
        return items[:limit]

    topic_tokens = eq.tokenize(report.topic)
    results = []
    for item in items:
        text = getattr(item, "text", "") or getattr(item, "title", "") or getattr(item, "snippet", "") or ""
        context = ""
        if source == "reddit":
            context = getattr(item, "subreddit", "")
        if source == "web":
            context = getattr(item, "source_domain", "")
        if domain == "weather":
            if not eq.is_weather_signal(text, topic_tokens, context):
                continue
        if domain == "macro":
            if not eq.is_macro_signal(text, topic_tokens, context):
                continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _render_nba_slate_board(report: schema.Report) -> list[str]:
    return []


def render_compact(report: schema.Report, limit: int = 15, missing_keys: str = "none") -> str:
    """Render compact output for the assistant to synthesize.

    Args:
        report: Report data
        limit: Max items per source
        missing_keys: 'both', 'reddit', 'x', or 'none'

    Returns:
        Compact markdown string
    """
    lines = []

    # Header
    if qt.detect_query_type(report.topic) == "market_watchlist":
        lines.append(f"## Market Watchlist Inputs: {report.topic}")
    else:
        lines.append(f"## Forecast Inputs: {report.topic}")
    lines.append("")

    # Assess data freshness and add honesty warning if needed
    freshness = _assess_data_freshness(report)
    if freshness["is_sparse"]:
        lines.append("**LIMITED RECENT DATA** - Few discussions from the last 24 hours.")
        lines.append(f"Only {freshness['total_recent']} item(s) confirmed from {report.range_from} to {report.range_to}.")
        lines.append("Results below may include older/evergreen content. Be transparent with the user about this.")
        lines.append("")

    # Web-only mode banner (when no API keys)
    if report.mode == "web-only":
        lines.append("**WEB SEARCH MODE** - assistant will search blogs, docs & news")
        lines.append("")
        lines.append("---")
        lines.append("**Want better results?** Add API keys to unlock richer Reddit, TikTok, Instagram & X data:")
        lines.append("- Reddit public search works without a paid scraper")
        lines.append("- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` -> official Reddit OAuth")
        lines.append("- `SCRAPECREATORS_API_KEY` is optional and improves Reddit comments + TikTok + Instagram")
        lines.append("- `XAI_API_KEY` -> X posts with real likes & reposts")
        lines.append("- `OPENAI_API_KEY` (optional) -> extra Reddit fallback/search")
        lines.append("- Edit `~/.config/last24hours/.env` to add keys")
        lines.append("---")
        lines.append("")

    # Cache indicator
    if report.from_cache:
        age_str = f"{report.cache_age_hours:.1f}h old" if report.cache_age_hours else "cached"
        lines.append(f"**CACHED RESULTS** ({age_str}) - use `--refresh` for fresh data")
        lines.append("")

    lines.append(f"**Date Range:** {report.range_from} to {report.range_to}")
    lines.append(f"**Mode:** {report.mode}")
    if report.openai_model_used:
        lines.append(f"**OpenAI Model:** {report.openai_model_used}")
    if report.xai_model_used:
        lines.append(f"**xAI Model:** {report.xai_model_used}")
    if report.resolved_x_handle:
        lines.append(f"**Resolved X Handle:** @{report.resolved_x_handle}")
    lines.append("")

    market_watchlist_summary = _render_market_watchlist_summary(report)
    if market_watchlist_summary:
        lines.extend(market_watchlist_summary)
    else:
        prediction_summary = _render_prediction_summary(report)
        if prediction_summary:
            lines.extend(prediction_summary)

    if report.weather:
        lines.append("### Official Weather")
        lines.append("")
        for item in report.weather[:limit]:
            probability = f"{item.probability_pct}%" if item.probability_pct is not None else "unknown"
            temp = f", {item.temperature} deg {item.temperature_unit}" if item.temperature is not None else ""
            wind = f", wind {item.wind}" if item.wind else ""
            lines.append(f"**{item.id}** {item.location} on {item.forecast_date}: peak precipitation {probability}")
            lines.append(f"  {item.short_forecast}{temp}{wind}")
            lines.append(f"  {item.url}")
            if item.why_relevant:
                lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Coverage note for partial coverage
    if report.mode == "reddit-only" and missing_keys in ("x", "none"):
        lines.append("*Tip: Add an xAI key (`XAI_API_KEY`) for X/Twitter data and better triangulation.*")
        lines.append("")
    elif report.mode == "x-only" and missing_keys in ("reddit", "none"):
        lines.append("*Tip: Reddit public search already works. Add Reddit OAuth credentials for the free upgraded path, or `SCRAPECREATORS_API_KEY` only if you want paid Reddit enrichment plus TikTok/Instagram coverage.*")
        lines.append("")

    # Reddit items
    if report.reddit_error:
        lines.append("### Reddit Threads")
        lines.append("")
        lines.append(f"**ERROR:** {report.reddit_error}")
        lines.append("")
    elif report.mode in ("both", "reddit-only") and not report.reddit:
        lines.append("### Reddit Threads")
        lines.append("")
        lines.append("*No relevant Reddit threads found for this topic.*")
        lines.append("")
    elif report.reddit:
        lines.append("### Reddit Threads")
        lines.append("")
        compact_reddit = _compact_sports_items(report.reddit, "reddit", report, limit)
        if compact_reddit == report.reddit[:limit]:
            compact_reddit = _compact_weather_macro_items(report.reddit, "reddit", report, limit)
        domain = _prediction_domain(report.topic)
        if not compact_reddit and (qt.detect_query_type(report.topic) == "prediction") and domain:
            lines.append(f"*No high-signal Reddit threads found for this {domain} forecast.*")
            lines.append("")
        elif not compact_reddit and qt.detect_query_type(report.topic) == "market_watchlist":
            lines.append("*Raw Reddit snippets suppressed in market-watchlist mode; catalyst snippets are included in the ranked picks when they clear quality filters.*")
            lines.append("")
        for item in compact_reddit:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.score is not None:
                    parts.append(f"{eng.score}pts")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments}cmt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** (score:{item.score}) r/{item.subreddit}{date_str}{conf_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")

            # Top comment (elevated: Reddit's value IS the comments)
            if item.top_comments and item.top_comments[0].score >= 10:
                tc = item.top_comments[0]
                excerpt = tc.excerpt[:200]
                if len(tc.excerpt) > 200:
                    excerpt = excerpt.rstrip() + "..."
                lines.append(f'  \U0001f4ac Top comment ({tc.score} upvotes): "{excerpt}"')

            # Comment insights
            if item.comment_insights:
                lines.append("  Insights:")
                for insight in item.comment_insights[:3]:
                    lines.append(f"    - {insight}")

            lines.append("")

    # X items
    if report.x_error:
        lines.append("### X Posts")
        lines.append("")
        lines.append(f"**ERROR:** {report.x_error}")
        lines.append("")
    elif report.mode in ("both", "x-only", "all", "x-web") and not report.x:
        lines.append("### X Posts")
        lines.append("")
        lines.append("*No relevant X posts found for this topic.*")
        lines.append("")
    elif report.x:
        lines.append("### X Posts")
        lines.append("")
        compact_x = _compact_sports_items(report.x, "x", report, limit)
        if compact_x == report.x[:limit]:
            compact_x = _compact_weather_macro_items(report.x, "x", report, limit)
        domain = _prediction_domain(report.topic)
        if not compact_x and (qt.detect_query_type(report.topic) == "prediction") and domain:
            lines.append(f"*No high-signal X posts found for this {domain} forecast.*")
            lines.append("")
        elif not compact_x and qt.detect_query_type(report.topic) == "market_watchlist":
            lines.append("*Raw X snippets suppressed in market-watchlist mode; catalyst snippets are included in the ranked picks when they clear quality filters.*")
            lines.append("")
        for item in compact_x:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.likes is not None:
                    parts.append(f"{eng.likes}likes")
                if eng.reposts is not None:
                    parts.append(f"{eng.reposts}rt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_handle}{date_str}{conf_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.text[:200]}...")
            lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # YouTube items
    if report.youtube_error:
        lines.append("### YouTube Videos")
        lines.append("")
        lines.append(f"**ERROR:** {report.youtube_error}")
        lines.append("")
    elif report.youtube:
        lines.append("### YouTube Videos")
        lines.append("")
        for item in report.youtube[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.views is not None:
                    parts.append(f"{eng.views:,} views")
                if eng.likes is not None:
                    parts.append(f"{eng.likes:,} likes")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) {item.channel_name}{date_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            if item.transcript_highlights:
                lines.append("  Highlights:")
                for hl in item.transcript_highlights[:5]:
                    lines.append(f'    - "{hl}"')
            if item.transcript_snippet:
                word_count = len(item.transcript_snippet.split())
                lines.append(f"  <details><summary>Full transcript ({word_count} words)</summary>")
                lines.append(f"  {item.transcript_snippet}")
                lines.append("  </details>")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # TikTok items
    if report.tiktok_error:
        lines.append("### TikTok Videos")
        lines.append("")
        lines.append(f"**ERROR:** {report.tiktok_error}")
        lines.append("")
    elif report.tiktok:
        lines.append("### TikTok Videos")
        lines.append("")
        for item in report.tiktok[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.views is not None:
                    parts.append(f"{eng.views:,} views")
                if eng.likes is not None:
                    parts.append(f"{eng.likes:,} likes")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_name}{date_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.text[:200]}")
            lines.append(f"  {item.url}")
            if item.caption_snippet and item.caption_snippet != item.text[:len(item.caption_snippet)]:
                snippet = item.caption_snippet[:200]
                if len(item.caption_snippet) > 200:
                    snippet += "..."
                lines.append(f"  Caption: {snippet}")
            if item.hashtags:
                lines.append(f"  Tags: {' '.join('#' + h for h in item.hashtags[:8])}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Instagram items
    if report.instagram_error:
        lines.append("### Instagram Reels")
        lines.append("")
        lines.append(f"**ERROR:** {report.instagram_error}")
        lines.append("")
    elif report.instagram:
        lines.append("### Instagram Reels")
        lines.append("")
        for item in report.instagram[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.views is not None:
                    parts.append(f"{eng.views:,} views")
                if eng.likes is not None:
                    parts.append(f"{eng.likes:,} likes")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_name}{date_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.text[:200]}")
            lines.append(f"  {item.url}")
            if item.caption_snippet and item.caption_snippet != item.text[:len(item.caption_snippet)]:
                snippet = item.caption_snippet[:200]
                if len(item.caption_snippet) > 200:
                    snippet += "..."
                lines.append(f"  Caption: {snippet}")
            if item.hashtags:
                lines.append(f"  Tags: {' '.join('#' + h for h in item.hashtags[:8])}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Hacker News items
    if report.hackernews_error:
        lines.append("### Hacker News Stories")
        lines.append("")
        lines.append(f"**ERROR:** {report.hackernews_error}")
        lines.append("")
    elif report.hackernews:
        lines.append("### Hacker News Stories")
        lines.append("")
        for item in report.hackernews[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.score is not None:
                    parts.append(f"{eng.score}pts")
                if eng.num_comments is not None:
                    parts.append(f"{eng.num_comments}cmt")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) hn/{item.author}{date_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.hn_url}")
            lines.append(f"  *{item.why_relevant}*")

            # Comment insights
            if item.comment_insights:
                lines.append(f"  Insights:")
                for insight in item.comment_insights[:3]:
                    lines.append(f"    - {insight}")

            lines.append("")

    # Bluesky items
    if report.bluesky_error:
        lines.append("### Bluesky Posts")
        lines.append("")
        lines.append(f"**ERROR:** {report.bluesky_error}")
        lines.append("")
    elif report.bluesky:
        bluesky_items = _compact_weather_macro_items(report.bluesky, "bluesky", report, limit)
        lines.append("### Bluesky Posts")
        lines.append("")
        if not bluesky_items and _prediction_domain(report.topic) in {"weather", "macro"}:
            label = "weather forecast" if _prediction_domain(report.topic) == "weather" else "macro forecast"
            lines.append(f"*No high-signal Bluesky posts found for this {label}.*")
            lines.append("")
        for item in bluesky_items[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.likes is not None:
                    parts.append(f"{eng.likes}lk")
                if eng.reposts is not None:
                    parts.append(f"{eng.reposts}rp")
                if eng.replies is not None:
                    parts.append(f"{eng.replies}re")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_handle}{date_str}{eng_str}{_xref_tag(item)}")
            if item.text:
                snippet = item.text[:200]
                if len(item.text) > 200:
                    snippet += "..."
                lines.append(f"  {snippet}")
            if item.url:
                lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Truth Social items
    if report.truthsocial_error:
        lines.append("### Truth Social Posts")
        lines.append("")
        lines.append(f"**ERROR:** {report.truthsocial_error}")
        lines.append("")
    elif report.truthsocial:
        truthsocial_items = _compact_weather_macro_items(report.truthsocial, "truthsocial", report, limit)
        lines.append("### Truth Social Posts")
        lines.append("")
        if not truthsocial_items and _prediction_domain(report.topic) in {"weather", "macro"}:
            label = "weather forecast" if _prediction_domain(report.topic) == "weather" else "macro forecast"
            lines.append(f"*No high-signal Truth Social posts found for this {label}.*")
            lines.append("")
        for item in truthsocial_items[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.likes is not None:
                    parts.append(f"{eng.likes}lk")
                if eng.reposts is not None:
                    parts.append(f"{eng.reposts}rp")
                if eng.replies is not None:
                    parts.append(f"{eng.replies}re")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}) @{item.author_handle}{date_str}{eng_str}{_xref_tag(item)}")
            if item.text:
                snippet = item.text[:200]
                if len(item.text) > 200:
                    snippet += "..."
                lines.append(f"  {snippet}")
            if item.url:
                lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    used_poly_ids, used_kalshi_ids = _used_market_ids(report)

    # Polymarket items
    if report.polymarket_error:
        lines.append("### Market Pricing (Polymarket)")
        lines.append("")
        lines.append(f"**ERROR:** {report.polymarket_error}")
        lines.append("")
    elif report.polymarket:
        lines.append("### Market Pricing (Polymarket)")
        lines.append("")
        market_items = report.polymarket
        if used_poly_ids:
            used_items = [item for item in report.polymarket if item.id in used_poly_ids]
            if len(report.forecasts) > 1:
                extra_items = [item for item in report.polymarket if item.id not in used_poly_ids and item.relevance >= 0.55]
                market_items = used_items + extra_items[:max(0, limit - len(used_items))]
            else:
                market_items = used_items
        elif qt.detect_query_type(report.topic) == "market_watchlist":
            market_items = []
        if _is_nba_slate_topic(report.topic):
            market_items = [item for item in market_items if _is_nba_market_item(item)]
        if not market_items and _is_nba_slate_topic(report.topic):
            lines.append("*No direct NBA game Polymarket markets found after league filtering.*")
            lines.append("")
        elif not market_items and qt.detect_query_type(report.topic) == "market_watchlist":
            lines.append("*No ranked Polymarket watchlist candidates shown beyond the summary above.*")
            lines.append("")
        for item in market_items[:limit]:
            eng_str = ""
            if item.engagement:
                eng = item.engagement
                parts = []
                if eng.volume is not None:
                    if eng.volume >= 1_000_000:
                        parts.append(f"${eng.volume/1_000_000:.1f}M volume")
                    elif eng.volume >= 1_000:
                        parts.append(f"${eng.volume/1_000:.0f}K volume")
                    else:
                        parts.append(f"${eng.volume:.0f} volume")
                if eng.liquidity is not None:
                    if eng.liquidity >= 1_000_000:
                        parts.append(f"${eng.liquidity/1_000_000:.1f}M liquidity")
                    elif eng.liquidity >= 1_000:
                        parts.append(f"${eng.liquidity/1_000:.0f}K liquidity")
                    else:
                        parts.append(f"${eng.liquidity:.0f} liquidity")
                if parts:
                    eng_str = f" [{', '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""

            lines.append(f"**{item.id}** (score:{item.score}){eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.question}")
            lines.append(f"  Type: {_format_market_type(getattr(item, 'market_type', 'unknown'))}")

            # Outcome prices with price movement
            if item.outcome_prices:
                outcomes = []
                for name, price in item.outcome_prices:
                    pct = price * 100
                    outcomes.append(f"{name}: {pct:.0f}%")
                outcome_line = " | ".join(outcomes)
                if item.outcomes_remaining > 0:
                    outcome_line += f" and {item.outcomes_remaining} more"
                if item.price_movement:
                    outcome_line += f" ({item.price_movement})"
                lines.append(f"  {outcome_line}")

            lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    if report.kalshi_error:
        lines.append("### Market Pricing (Kalshi)")
        lines.append("")
        lines.append(f"**ERROR:** {report.kalshi_error}")
        lines.append("")
    elif report.kalshi:
        lines.append("### Market Pricing (Kalshi)")
        lines.append("")
        kalshi_items = report.kalshi
        if used_kalshi_ids:
            used_items = [item for item in report.kalshi if item.id in used_kalshi_ids]
            if len(report.forecasts) > 1:
                extra_items = [item for item in report.kalshi if item.id not in used_kalshi_ids and item.relevance >= 0.55]
                kalshi_items = used_items + extra_items[:max(0, limit - len(used_items))]
            else:
                kalshi_items = used_items
        elif qt.detect_query_type(report.topic) == "market_watchlist":
            kalshi_items = []
        if _is_nba_slate_topic(report.topic):
            kalshi_items = [item for item in kalshi_items if _is_nba_market_item(item)]
        if not kalshi_items and _is_nba_slate_topic(report.topic):
            lines.append("*No direct NBA game Kalshi markets found after league filtering.*")
            lines.append("")
        elif not kalshi_items and qt.detect_query_type(report.topic) == "market_watchlist":
            lines.append("*No ranked Kalshi watchlist candidates shown beyond the summary above.*")
            lines.append("")
        for item in kalshi_items[:limit]:
            eng_str = ""
            if item.engagement:
                parts = []
                if item.engagement.volume is not None:
                    parts.append(f"{item.engagement.volume:,.0f} vol")
                if item.engagement.open_interest is not None:
                    parts.append(f"{item.engagement.open_interest:,.0f} OI")
                if item.engagement.liquidity is not None:
                    parts.append(f"${item.engagement.liquidity:,.0f} liq")
                if parts:
                    eng_str = f" [{' | '.join(parts)}]"

            date_str = f" ({item.date})" if item.date else ""
            lines.append(f"**{item.id}** (score:{item.score}) {item.ticker}{date_str}{eng_str}{_xref_tag(item)}")
            lines.append(f"  {item.question}")
            lines.append(f"  Type: {_format_market_type(getattr(item, 'market_type', 'unknown'))}")
            market_line = []
            if item.current_probability is not None:
                market_line.append(f"YES: {item.current_probability * 100:.0f}%")
            if item.price_movement:
                market_line.append(item.price_movement)
            if item.end_date:
                market_line.append(f"expires {item.end_date}")
            if market_line:
                lines.append(f"  {' | '.join(market_line)}")
            if item.title:
                lines.append(f"  Event: {item.title}")
            lines.append(f"  {item.url}")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    # Web items (if any - populated by the assistant)
    if report.web_error:
        lines.append("### Web Results")
        lines.append("")
        lines.append(f"**ERROR:** {report.web_error}")
        lines.append("")
    elif report.web:
        lines.append("### Web Results")
        lines.append("")
        compact_web = _compact_weather_macro_items(report.web, "web", report, limit)
        domain = _prediction_domain(report.topic)
        if not compact_web and qt.detect_query_type(report.topic) == "prediction" and domain in {"weather", "macro"}:
            lines.append(f"*No high-signal web results found for this {domain} forecast.*")
            lines.append("")
        for item in compact_web:
            date_str = f" ({item.date})" if item.date else " (date unknown)"
            conf_str = f" [date:{item.date_confidence}]" if item.date_confidence != "high" else ""

            lines.append(f"**{item.id}** [WEB] (score:{item.score}) {item.source_domain}{date_str}{conf_str}{_xref_tag(item)}")
            lines.append(f"  {item.title}")
            lines.append(f"  {item.url}")
            lines.append(f"  {item.snippet[:150]}...")
            lines.append(f"  *{item.why_relevant}*")
            lines.append("")

    return "\n".join(lines)


def render_source_status(report: schema.Report, source_info: dict = None) -> str:
    """Render source status footer showing what was used/skipped and why.

    Args:
        report: Report data
        source_info: Dict with source availability info:
            x_skip_reason, youtube_skip_reason, web_skip_reason

    Returns:
        Source status markdown string
    """
    if source_info is None:
        source_info = {}

    lines = []
    lines.append("---")
    lines.append("**Sources:**")

    # Reddit
    if report.reddit_error:
        lines.append(f"  ERROR Reddit: {report.reddit_error}")
    elif report.reddit:
        source_label = {
            "reddit_oauth": "Reddit OAuth",
            "reddit_public": "Reddit public JSON",
            "scrapecreators": "ScrapeCreators",
        }.get(source_info.get("reddit_source"), "Reddit")
        line = f"  OK {source_label}: {len(report.reddit)} threads"
        if source_info.get("reddit_rate_remaining") is not None:
            line += f" (rate remaining: {source_info.get('reddit_rate_remaining')})"
        lines.append(line)
        if source_info.get("reddit_warning"):
            lines.append(f"  WARN Reddit: {source_info['reddit_warning']}")
    elif report.mode in ("both", "reddit-only", "all", "reddit-web"):
        pass  # Hide zero-result sources
    else:
        reason = source_info.get("reddit_skip_reason", "not configured")
        lines.append(f"  SKIP Reddit: {reason}")

    # X
    if report.x_error:
        lines.append(f"  ERROR X: {report.x_error}")
    elif report.x:
        x_line = f"  OK X: {len(report.x)} posts"
        if report.resolved_x_handle:
            x_line += f" (via @{report.resolved_x_handle} + keyword search)"
        lines.append(x_line)
    elif report.mode in ("both", "x-only", "all", "x-web"):
        pass  # Hide zero-result sources
    else:
        reason = source_info.get("x_skip_reason", "No Bird CLI or XAI_API_KEY")
        lines.append(f"  SKIP X: {reason}")

    # YouTube
    if report.youtube_error:
        lines.append(f"  ERROR YouTube: {report.youtube_error}")
    elif report.youtube:
        with_transcripts = sum(1 for v in report.youtube if getattr(v, 'transcript_snippet', None))
        lines.append(f"  OK YouTube: {len(report.youtube)} videos ({with_transcripts} with transcripts)")
    # Hide when zero results (no skip reason line needed)

    # TikTok
    if report.tiktok_error:
        lines.append(f"  ERROR TikTok: {report.tiktok_error}")
    elif report.tiktok:
        with_captions = sum(1 for v in report.tiktok if getattr(v, 'caption_snippet', None))
        lines.append(f"  OK TikTok: {len(report.tiktok)} videos ({with_captions} with captions)")
    # Hide when zero results

    # Instagram
    if report.instagram_error:
        lines.append(f"  ERROR Instagram: {report.instagram_error}")
    elif report.instagram:
        with_captions = sum(1 for v in report.instagram if getattr(v, 'caption_snippet', None))
        lines.append(f"  OK Instagram: {len(report.instagram)} reels ({with_captions} with captions)")
    # Hide when zero results

    # Xiaohongshu (from Web source bucket)
    xhs_count = 0
    if report.web:
        xhs_count = sum(
            1 for w in report.web
            if getattr(w, "source_domain", "").lower().endswith("xiaohongshu.com")
        )
    if xhs_count > 0:
        lines.append(f"  OK Xiaohongshu: {xhs_count} notes")
    else:
        reason = source_info.get("xiaohongshu_skip_reason")
        if reason:
            lines.append(f"  WARN Xiaohongshu: {reason}")

    # Hacker News
    if report.hackernews_error:
        lines.append(f"  ERROR HN: {report.hackernews_error}")
    elif report.hackernews:
        lines.append(f"  OK HN: {len(report.hackernews)} stories")
    # Hide when zero results

    # Bluesky
    if report.bluesky_error:
        lines.append(f"  ERROR Bluesky: {report.bluesky_error}")
    elif report.bluesky:
        lines.append(f"  OK Bluesky: {len(report.bluesky)} posts")
    # Hide when zero results

    # Truth Social
    if report.truthsocial_error:
        lines.append(f"  ERROR Truth Social: {report.truthsocial_error}")
    elif report.truthsocial:
        lines.append(f"  OK Truth Social: {len(report.truthsocial)} posts")
    # Hide when zero results

    # Polymarket
    if report.polymarket_error:
        lines.append(f"  ERROR Polymarket: {report.polymarket_error}")
    elif report.polymarket:
        lines.append(f"  OK Polymarket: {len(report.polymarket)} markets")
    # Hide when zero results

    if report.kalshi_error:
        lines.append(f"  ERROR Kalshi: {report.kalshi_error}")
    elif report.kalshi:
        lines.append(f"  OK Kalshi: {len(report.kalshi)} markets")

    # Web
    if report.web_error:
        lines.append(f"  ERROR Web: {report.web_error}")
    elif report.web:
        lines.append(f"  OK Web: {len(report.web)} pages")
    else:
        reason = source_info.get("web_skip_reason", "assistant will use WebSearch")
        lines.append(f"  WARN Web: {reason}")

    if report.weather_error:
        lines.append(f"  Weather: error - {report.weather_error}")
    elif report.weather:
        lines.append(f"  Weather: {len(report.weather)} NWS forecast")

    lines.append("")
    return "\n".join(lines)


def render_context_snippet(report: schema.Report) -> str:
    """Render reusable context snippet.

    Args:
        report: Report data

    Returns:
        Context markdown string
    """
    lines = []
    lines.append(f"# Context: {report.topic} (Last 24 Hours)")
    lines.append("")
    lines.append(f"*Generated: {report.generated_at[:10]} | Sources: {report.mode}*")
    lines.append("")

    if report.forecasts:
        lines.append("## Forecast Summary")
        lines.append("")
        for item in report.forecasts[:5]:
            lines.append(f"- {item.title}: {_format_probability_range(item)} via {_anchor_label(item)}")
        lines.append("")
    if report.market_watchlist:
        lines.append("## Market Watchlist Summary")
        lines.append("")
        for item in report.market_watchlist[:5]:
            lines.append(f"- {item.id}: {item.title or item.question} - {_format_watch_probability(item)} via {item.venue}")
        lines.append("")

    # Key sources summary
    lines.append("## Key Sources")
    lines.append("")

    all_items = []
    for item in report.reddit[:5]:
        all_items.append((item.score, "Reddit", item.title, item.url))
    for item in report.x[:5]:
        all_items.append((item.score, "X", item.text[:50] + "...", item.url))
    for item in report.tiktok[:5]:
        all_items.append((item.score, "TikTok", item.text[:50] + "...", item.url))
    for item in report.instagram[:5]:
        all_items.append((item.score, "Instagram", item.text[:50] + "...", item.url))
    for item in report.hackernews[:5]:
        all_items.append((item.score, "HN", item.title[:50] + "...", item.hn_url))
    for item in report.bluesky[:5]:
        all_items.append((item.score, "Bluesky", item.text[:50] + "...", item.url))
    for item in report.truthsocial[:5]:
        all_items.append((item.score, "Truth Social", item.text[:50] + "...", item.url))
    for item in report.polymarket[:5]:
        all_items.append((item.score, "Polymarket", item.question[:50] + "...", item.url))
    for item in report.kalshi[:5]:
        all_items.append((item.score, "Kalshi", item.question[:50] + "...", item.url))
    for item in report.market_watchlist[:5]:
        all_items.append((item.rank_score, "MarketWatch", item.question[:50] + "...", item.url))
    for item in report.weather[:5]:
        all_items.append((item.score, "Weather", item.title[:50] + "...", item.url))
    for item in report.web[:5]:
        all_items.append((item.score, "Web", item.title[:50] + "...", item.url))

    all_items.sort(key=lambda x: -x[0])
    for score, source, text, url in all_items[:7]:
        lines.append(f"- [{source}] {text}")

    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("*See full report for best practices, prompt pack, and detailed sources.*")
    lines.append("")

    return "\n".join(lines)


def render_full_report(report: schema.Report) -> str:
    """Render full markdown report.

    Args:
        report: Report data

    Returns:
        Full report markdown
    """
    lines = []

    # Title
    if qt.detect_query_type(report.topic) == "market_watchlist":
        lines.append(f"# {report.topic} - Last 24 Hours Market Watchlist Inputs")
    else:
        lines.append(f"# {report.topic} - Last 24 Hours Forecast Inputs")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Date Range:** {report.range_from} to {report.range_to}")
    lines.append(f"**Mode:** {report.mode}")
    lines.append("")

    if report.forecasts:
        lines.append("## Forecast Summary")
        lines.append("")
        for item in report.forecasts:
            lines.append(f"### {item.title}")
            lines.append("")
            lines.append(f"- **Forecast:** {_forecast_display_label(item)} {_format_probability_range(item)}")
            lines.append(f"- **Anchor:** {_anchor_label(item)}")
            lines.append(f"- **Market View:** {item.market_view}")
            lines.append(f"- **Confidence:** {item.confidence_level}")
            if item.uncertainty:
                lines.append(f"- **Uncertainty:** {item.uncertainty}")
            lines.append("")

    if report.market_watchlist:
        lines.append("## Market Picks To Watch")
        lines.append("")
        lines.append("*Informational market-monitoring output, not trade execution or allocation advice.*")
        lines.append("")
        for item in report.market_watchlist:
            lines.append(f"### {item.id}: {item.title or item.question}")
            lines.append("")
            lines.append(f"- **Pick:** {item.venue} - {_format_watch_probability(item)}")
            lines.append(f"- **Why it ranks:** {item.why_ranks} (rank score {item.rank_score}/100)")
            lines.append(f"- **Market signal:** {item.market_signal}")
            lines.append(f"- **Catalyst / evidence:** {item.catalyst_summary}")
            lines.append(f"- **Risk / what would change it:** {item.risk}")
            if item.cross_market_note:
                lines.append(f"- **Cross-market note:** {item.cross_market_note}")
            if item.evidence_refs:
                lines.append(f"- **Evidence refs:** {', '.join(item.evidence_refs[:5])}")
            if item.url:
                lines.append(f"- **URL:** {item.url}")
            lines.append("")

    # Models
    lines.append("## Models Used")
    lines.append("")
    if report.openai_model_used:
        lines.append(f"- **OpenAI:** {report.openai_model_used}")
    if report.xai_model_used:
        lines.append(f"- **xAI:** {report.xai_model_used}")
    lines.append("")

    # Reddit section
    if report.reddit:
        lines.append("## Reddit Threads")
        lines.append("")
        for item in report.reddit:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Subreddit:** r/{item.subreddit}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.score or '?'} points, {eng.num_comments or '?'} comments")

            if item.top_comments and item.top_comments[0].score >= 10:
                tc = item.top_comments[0]
                excerpt = tc.excerpt[:200]
                if len(tc.excerpt) > 200:
                    excerpt = excerpt.rstrip() + "..."
                lines.append("")
                lines.append(f'**\U0001f4ac Top Comment** ({tc.score} upvotes, u/{tc.author}):')
                lines.append(f'> {excerpt}')

            if item.comment_insights:
                lines.append("")
                lines.append("**Key Insights from Comments:**")
                for insight in item.comment_insights:
                    lines.append(f"- {insight}")

            lines.append("")

    # X section
    if report.x:
        lines.append("## X Posts")
        lines.append("")
        for item in report.x:
            lines.append(f"### {item.id}: @{item.author_handle}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.likes or '?'} likes, {eng.reposts or '?'} reposts")

            lines.append("")
            lines.append(f"> {item.text}")
            lines.append("")

    # TikTok section
    if report.tiktok:
        lines.append("## TikTok Videos")
        lines.append("")
        for item in report.tiktok:
            lines.append(f"### {item.id}: @{item.author_name}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.views or '?'} views, {eng.likes or '?'} likes, {eng.num_comments or '?'} comments")

            if item.hashtags:
                lines.append(f"- **Hashtags:** {' '.join('#' + h for h in item.hashtags[:10])}")

            lines.append("")
            lines.append(f"> {item.text[:300]}")
            lines.append("")

    # Instagram section
    if report.instagram:
        lines.append("## Instagram Reels")
        lines.append("")
        for item in report.instagram:
            lines.append(f"### {item.id}: @{item.author_name}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.views or '?'} views, {eng.likes or '?'} likes, {eng.num_comments or '?'} comments")

            if item.hashtags:
                lines.append(f"- **Hashtags:** {' '.join('#' + h for h in item.hashtags[:10])}")

            lines.append("")
            lines.append(f"> {item.text[:300]}")
            lines.append("")

    # HN section
    if report.hackernews:
        lines.append("## Hacker News Stories")
        lines.append("")
        for item in report.hackernews:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Author:** {item.author}")
            lines.append(f"- **HN URL:** {item.hn_url}")
            if item.url:
                lines.append(f"- **Article URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.score or '?'} points, {eng.num_comments or '?'} comments")

            if item.comment_insights:
                lines.append("")
                lines.append("**Key Insights from Comments:**")
                for insight in item.comment_insights:
                    lines.append(f"- {insight}")

            lines.append("")

    # Bluesky section
    if report.bluesky:
        lines.append("## Bluesky Posts")
        lines.append("")
        for item in report.bluesky:
            lines.append(f"### {item.id}: @{item.author_handle}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.likes or '?'} likes, {eng.reposts or '?'} reposts, {eng.replies or '?'} replies")

            lines.append("")
            lines.append(f"> {item.text[:300]}")
            lines.append("")

    # Truth Social section
    if report.truthsocial:
        lines.append("## Truth Social Posts")
        lines.append("")
        for item in report.truthsocial:
            lines.append(f"### {item.id}: @{item.author_handle}")
            lines.append("")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")

            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Engagement:** {eng.likes or '?'} likes, {eng.reposts or '?'} reposts, {eng.replies or '?'} replies")

            lines.append("")
            lines.append(f"> {item.text[:300]}")
            lines.append("")

    # Polymarket section
    if report.polymarket:
        lines.append("## Market Pricing (Polymarket)")
        lines.append("")
        for item in report.polymarket:
            lines.append(f"### {item.id}: {item.question}")
            lines.append("")
            lines.append(f"- **Event:** {item.title}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")

            if item.outcome_prices:
                outcomes = [f"{name}: {price*100:.0f}%" for name, price in item.outcome_prices]
                lines.append(f"- **Outcomes:** {' | '.join(outcomes)}")
            if item.price_movement:
                lines.append(f"- **Trend:** {item.price_movement}")
            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Volume:** ${eng.volume or 0:,.0f} | Liquidity: ${eng.liquidity or 0:,.0f}")

            lines.append("")

    if report.kalshi:
        lines.append("## Market Pricing (Kalshi)")
        lines.append("")
        for item in report.kalshi:
            lines.append(f"### {item.id}: {item.question}")
            lines.append("")
            lines.append(f"- **Event:** {item.title}")
            lines.append(f"- **Ticker:** {item.ticker}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'}")
            lines.append(f"- **Score:** {item.score}/100")
            if item.current_probability is not None:
                lines.append(f"- **Implied probability:** {item.current_probability * 100:.0f}%")
            if item.price_movement:
                lines.append(f"- **Trend:** {item.price_movement}")
            if item.engagement:
                eng = item.engagement
                lines.append(f"- **Volume:** {eng.volume or 0:,.0f} | Open interest: {eng.open_interest or 0:,.0f} | Liquidity: ${eng.liquidity or 0:,.0f}")
            if item.end_date:
                lines.append(f"- **Expiration:** {item.end_date}")
            lines.append("")

    # Web section
    if report.web:
        lines.append("## Web Results")
        lines.append("")
        for item in report.web:
            lines.append(f"### {item.id}: {item.title}")
            lines.append("")
            lines.append(f"- **Source:** {item.source_domain}")
            lines.append(f"- **URL:** {item.url}")
            lines.append(f"- **Date:** {item.date or 'Unknown'} (confidence: {item.date_confidence})")
            lines.append(f"- **Score:** {item.score}/100")
            lines.append(f"- **Relevance:** {item.why_relevant}")
            lines.append("")
            lines.append(f"> {item.snippet}")
            lines.append("")

    # Placeholders for assistant synthesis
    lines.append("## Best Practices")
    lines.append("")
    lines.append("*To be synthesized by assistant*")
    lines.append("")

    lines.append("## Prompt Pack")
    lines.append("")
    lines.append("*To be synthesized by assistant*")
    lines.append("")

    return "\n".join(lines)




def write_outputs(
    report: schema.Report,
    raw_openai: Optional[dict] = None,
    raw_xai: Optional[dict] = None,
    raw_reddit_enriched: Optional[list] = None,
):
    """Write all output files.

    Args:
        report: Report data
        raw_openai: Raw OpenAI API response
        raw_xai: Raw xAI API response
        raw_reddit_enriched: Raw enriched Reddit thread data
    """
    ensure_output_dir()

    # report.json
    _write_json(OUTPUT_DIR / "report.json", report.to_dict())

    # report.md
    _write_text(OUTPUT_DIR / "report.md", render_full_report(report))

    # last24hours.context.md
    _write_text(OUTPUT_DIR / "last24hours.context.md", render_context_snippet(report))

    # Raw responses
    if raw_openai:
        _write_json(OUTPUT_DIR / "raw_openai.json", raw_openai)

    if raw_xai:
        _write_json(OUTPUT_DIR / "raw_xai.json", raw_xai)

    if raw_reddit_enriched:
        _write_json(OUTPUT_DIR / "raw_reddit_threads_enriched.json", raw_reddit_enriched)


def get_context_path() -> str:
    """Get path to context file."""
    return str(OUTPUT_DIR / "last24hours.context.md")
