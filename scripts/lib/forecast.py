"""Market-anchored forecast synthesis for prediction queries."""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from . import evidence_fusion, evidence_quality as eq, market_types, query_type as qt, schema

LOW_SIGNAL_SOCIAL_TERMS = eq.LOW_SIGNAL_SOCIAL_TERMS
DRIVER_TERMS = eq.DRIVER_TERMS
WEATHER_SIGNAL_TERMS = eq.WEATHER_SIGNAL_TERMS
WEATHER_WEAK_TERMS = eq.WEATHER_WEAK_TERMS
MACRO_SIGNAL_TERMS = eq.MACRO_SIGNAL_TERMS
MACRO_STRONG_TERMS = eq.MACRO_STRONG_TERMS
MACRO_CONTEXT_TERMS = eq.MACRO_CONTEXT_TERMS
MACRO_SUPPORT_TERMS = eq.MACRO_SUPPORT_TERMS
RECESSION_SUPPORT_TERMS = eq.RECESSION_SUPPORT_TERMS
MACRO_BAD_CONTEXT_TERMS = eq.MACRO_BAD_CONTEXT_TERMS
SPORTS_DRIVER_TERMS = eq.SPORTS_DRIVER_TERMS
SPORTS_HIGH_SIGNAL_TERMS = eq.SPORTS_HIGH_SIGNAL_TERMS
SPORTS_MARKET_CONTEXT_TERMS = eq.SPORTS_MARKET_CONTEXT_TERMS
SPORTS_LOW_SIGNAL_TERMS = eq.SPORTS_LOW_SIGNAL_TERMS
SPORTS_RECAP_TERMS = eq.SPORTS_RECAP_TERMS
SPORTS_REPORTER_TOKENS = eq.SPORTS_REPORTER_TOKENS
SPORTS_TEAM_TOKENS = eq.SPORTS_TEAM_TOKENS
_NBA_CODE_TO_TEAM = {
    "ATL": "hawks",
    "BOS": "celtics",
    "BKN": "nets",
    "CHA": "hornets",
    "CHI": "bulls",
    "CLE": "cavaliers",
    "DAL": "mavericks",
    "DEN": "nuggets",
    "DET": "pistons",
    "GSW": "warriors",
    "HOU": "rockets",
    "IND": "pacers",
    "LAC": "clippers",
    "LAL": "lakers",
    "MEM": "grizzlies",
    "MIA": "heat",
    "MIL": "bucks",
    "MIN": "timberwolves",
    "NOP": "pelicans",
    "NYK": "knicks",
    "OKC": "thunder",
    "ORL": "magic",
    "PHI": "76ers",
    "PHX": "suns",
    "POR": "blazers",
    "SAC": "kings",
    "SAS": "spurs",
    "TOR": "raptors",
    "UTA": "jazz",
    "WAS": "wizards",
}


@dataclass
class _EvidenceCandidate:
    score: float
    text: str
    tokens: set[str]
    source: str
    team_hits: int
    signal_hits: int


@dataclass(frozen=True)
class _ThresholdSpec:
    entity: Optional[str]
    direction: Optional[str]
    threshold: Optional[float]
    window: Optional[str]


def _tokenize(text: str) -> set[str]:
    return eq.tokenize(text)


def _matchup_side_tokens(text: str) -> list[set[str]]:
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


_ESPORTS_MATCH_NOISE = {
    "counter", "strike", "counterstrike", "counter-strike", "esports", "valorant", "lol",
    "bo1", "bo2", "bo3", "bo5", "group", "stage", "regular", "playoffs", "playoff",
    "qualifier", "qualifiers", "online", "league", "series", "main", "european",
    "world", "cup", "north", "america", "rivals", "blast", "conquest", "prague",
}


def _esports_matchup_side_tokens(text: str) -> list[set[str]]:
    text_lower = text.lower()
    separator = None
    for candidate in (" vs. ", " vs ", " at "):
        if candidate in text_lower:
            separator = candidate
            break
    if not separator:
        return []
    sides = []
    for raw_side in text_lower.split(separator, 1):
        side = raw_side.split(" - ", 1)[0]
        side = re.sub(r"\([^)]*\)", " ", side)
        if ":" in side:
            side = side.rsplit(":", 1)[-1]
        tokens = {
            token
            for token in re.sub(r"[^\w\s]", " ", side).split()
            if len(token) >= 2 and token not in _ESPORTS_MATCH_NOISE
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


def _signature_from_kalshi_codes(text: str) -> Optional[str]:
    match = re.search(r"KXNBAGAME-\d{2}[A-Z]{3}\d{2}([A-Z]{3})([A-Z]{3})", (text or "").upper())
    if not match:
        return None
    left = _NBA_CODE_TO_TEAM.get(match.group(1))
    right = _NBA_CODE_TO_TEAM.get(match.group(2))
    if not left or not right:
        return None
    teams = sorted([left, right])
    return " | ".join(teams)


def _item_matchup_signature(item) -> Optional[str]:
    kalshi_text = " ".join(
        str(part) for part in (
            getattr(item, "ticker", ""),
            getattr(item, "event_ticker", ""),
            getattr(item, "url", ""),
        )
        if part
    )
    base_text = (
        getattr(item, "title", "")
        or getattr(item, "question", "")
        or " ".join(
            str(part) for part in (
                getattr(item, "title", ""),
                getattr(item, "question", ""),
            )
            if part
        )
    )
    if eq.is_esports_query(str(base_text)):
        sides = _esports_matchup_side_tokens(str(base_text))
        if len(sides) == 2:
            normalized = [" ".join(sorted(side)) for side in sides]
            normalized.sort()
            return " | ".join(normalized)
    return _signature_from_kalshi_codes(kalshi_text) or _matchup_signature(str(base_text))


def market_quality(engagement: Optional[schema.Engagement], movement_pct: Optional[float] = None) -> float:
    """Return a 0-1 market quality score shared by both venues."""
    if engagement is None:
        return 0.0
    volume = math.log1p(engagement.volume or 0.0)
    liquidity = math.log1p(engagement.liquidity or 0.0)
    open_interest = math.log1p(engagement.open_interest or 0.0)
    movement = min(1.0, abs(movement_pct or 0.0) / 20.0)
    raw = 0.45 * volume + 0.25 * liquidity + 0.20 * open_interest + 0.10 * movement
    return min(1.0, raw / 6.5) if raw > 0 else 0.0


def _clean_outcome_label(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", (name or "")).strip()
    if not cleaned:
        return ""
    if cleaned.lower() in {"the", "there", "1", "2", "3", "4", "5"}:
        return ""
    return cleaned


def _top_polymarket_probability(item: schema.PolymarketItem) -> tuple[Optional[str], Optional[float]]:
    if not item.outcome_prices:
        return None, None
    ordered = sorted(item.outcome_prices, key=lambda pair: pair[1], reverse=True)
    label = _clean_outcome_label(ordered[0][0]) or None
    return label, ordered[0][1]


def _polymarket_probability_for_topic(
    item: schema.PolymarketItem,
    topic: str,
) -> tuple[Optional[str], Optional[float]]:
    """Return the probability for the requested event side when identifiable."""
    topic_spec = _threshold_spec(topic)
    market_spec = _threshold_spec(f"{item.title} {item.question}")
    if (
        item.outcome_prices
        and topic_spec.direction in {"above", "below"}
        and market_spec.direction in {"above", "below"}
        and topic_spec.direction == market_spec.direction
    ):
        for label, probability in item.outcome_prices:
            if str(label).strip().lower() == "yes":
                return "Yes", probability
    return _top_polymarket_probability(item)


def _topic_tokens(topic: str) -> set[str]:
    stop = {"will", "the", "for", "and", "today", "tomorrow", "tonight", "odds", "probability"}
    return {
        token for token in re.sub(r"[^\w\s]", " ", topic.lower()).split()
        if len(token) > 2 and token not in stop
    }


_MONTH_TOKENS = {
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep", "sept",
    "september", "oct", "october", "nov", "november", "dec", "december",
}

_MONTH_NUMBERS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_CRYPTO_ENTITY_ALIASES = {
    "bitcoin": {"bitcoin", "btc", "xbt"},
    "ethereum": {"ethereum", "ether", "eth"},
    "solana": {"solana", "sol"},
    "dogecoin": {"dogecoin", "doge"},
}
_CRYPTO_ENTITY_TOKENS = set().union(*_CRYPTO_ENTITY_ALIASES.values())
_MACRO_LOW_SIGNAL_PHRASES = {
    "top traders",
    "betting big",
    "stop missing out",
    "keep cashing",
    "signal room",
    "vip picks",
    "regime alert",
    "most popular bets",
    "free picks",
    "daily winners",
}
_CRYPTO_LOW_SIGNAL_PHRASES = {
    "betting big",
    "market manipulation",
    "holding it down",
    "vote a or b",
    "quick btc poll",
    "should be above",
    "most popular bets",
    "free picks",
    "top traders",
}
_CRYPTO_STRONG_SIGNAL_TERMS = {
    "spot", "etf", "flow", "flows", "liquidity", "liquidation", "liquidations",
    "support", "resistance", "breakout", "repricing", "exchange", "exchanges",
    "momentum", "volume",
}
_CRYPTO_PRIMARY_MARKET_TERMS = {
    "spot", "etf", "flow", "flows", "liquidity", "exchange", "exchanges", "repricing",
}
_MACRO_STRONG_CONTEXT_TERMS = {
    "official", "officials", "governor", "chair", "statement", "statements",
    "remarks", "meeting", "minutes", "data", "release", "releases", "payrolls",
    "jobs", "inflation", "cpi", "yield", "yields", "treasury", "treasuries",
}
_SOCIAL_SOURCES = {"x", "reddit"}
_SOCIAL_PROMO_TOKENS = {
    "alert", "alerts", "vip", "bets", "bet", "betting", "pick", "picks",
    "tail", "lock", "locks", "parlay", "parlays", "cashing", "winner",
    "winners", "poll", "polls", "vote", "votes", "trader", "traders",
    "followers", "subscribe",
}
_OFFICIAL_MACRO_DOMAINS = {
    "federalreserve.gov",
    "bls.gov",
    "bea.gov",
    "treasury.gov",
    "census.gov",
    "fred.stlouisfed.org",
}
_MARKET_CONTEXT_DOMAINS = {
    "polymarket.com",
    "kalshi.com",
    "cmegroup.com",
}
_QUALITY_WEB_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "apnews.com",
}


def _is_crypto_query(text: str) -> bool:
    tokens = _tokenize(text)
    return bool(_threshold_entity(text) or (tokens & _CRYPTO_ENTITY_TOKENS))


def _looks_like_alert_spam(text: str) -> bool:
    raw = (text or "").strip()
    letters = [char for char in raw if char.isalpha()]
    uppercase = [char for char in letters if char.isupper()]
    upper_ratio = (len(uppercase) / len(letters)) if letters else 0.0
    tokens = raw.split()
    loud_tokens = sum(1 for token in tokens if len(token) >= 4 and token.isupper())
    return upper_ratio >= 0.45 or loud_tokens >= 4


def _source_kind(source: str) -> str:
    return str(source or "generic").strip().lower()


def _source_context_bonus(source: str, source_context: str = "") -> float:
    source_name = _source_kind(source)
    context = str(source_context or "").lower()
    if any(domain in context for domain in _OFFICIAL_MACRO_DOMAINS):
        return 18.0
    if any(domain in context for domain in _MARKET_CONTEXT_DOMAINS):
        return 12.0
    if any(domain in context for domain in _QUALITY_WEB_DOMAINS):
        return 8.0
    if source_name == "web":
        return 6.0
    if source_name == "hackernews":
        return 3.0
    if source_name == "reddit":
        return -6.0
    if source_name == "x":
        return -10.0
    return 0.0


def _social_macro_context_ok(tokens: set[str], title_tokens: set[str]) -> bool:
    macro_overlap = len((title_tokens - {"will", "have", "us", "usa", "by", "in", "end", "next", "month", "year"}) & tokens)
    anchor_terms = tokens & {"fed", "fomc", "powell"}
    support_terms = tokens & {
        "cpi", "jobs", "payrolls", "yield", "yields", "treasury", "treasuries",
        "pricing", "priced", "market", "markets", "statement", "statements",
        "remarks", "minutes", "official", "officials", "governor",
    }
    strong_terms = tokens & (MACRO_STRONG_TERMS | _MACRO_STRONG_CONTEXT_TERMS)
    return macro_overlap >= 2 and bool(anchor_terms) and bool(support_terms) and len(strong_terms) >= 2


def _macro_social_lead_ok(tokens: set[str]) -> bool:
    return bool(tokens & {"fed", "fomc", "powell"}) and len(tokens & (MACRO_STRONG_TERMS | _MACRO_STRONG_CONTEXT_TERMS)) >= 3


def _macro_quality_lead_ok(candidate: _EvidenceCandidate) -> bool:
    tokens = candidate.tokens
    if candidate.source in _SOCIAL_SOURCES:
        return False
    if not (tokens & {"fed", "fomc", "powell"}):
        return False
    if not (tokens & (MACRO_STRONG_TERMS | _MACRO_STRONG_CONTEXT_TERMS)):
        return False
    if candidate.source == "web":
        has_quality_domain = bool(tokens & {"federalreserve", "bls", "bea", "treasury", "fred", "reuters", "bloomberg", "wsj", "ft", "apnews"})
        return has_quality_domain or bool(tokens & {"official", "officials", "governor", "statement", "remarks", "minutes", "cpi", "jobs", "payrolls", "yield", "yields", "treasury", "treasuries"})
    return bool(tokens & {"official", "officials", "governor", "statement", "remarks", "minutes", "cpi", "jobs", "payrolls", "yield", "yields", "treasury", "treasuries"})


def _social_crypto_context_ok(tokens: set[str], title_tokens: set[str]) -> bool:
    topic_entities = title_tokens & _CRYPTO_ENTITY_TOKENS
    if topic_entities and not (topic_entities & tokens):
        return False
    strong_terms = tokens & (_CRYPTO_STRONG_SIGNAL_TERMS | {"spot", "price", "prices"})
    if {"poll", "polls", "vote", "votes"} & tokens:
        return False
    if topic_entities:
        return len(strong_terms) >= 2
    overlap = len((title_tokens - {"this", "week", "month", "year", "price"}) & tokens)
    return overlap >= 2 and len(strong_terms) >= 2


def _social_crypto_threshold_match_ok(title: str, text: str) -> bool:
    topic_spec = _threshold_spec(title)
    if topic_spec.threshold is None:
        return True
    evidence_spec = _threshold_spec(text)
    if evidence_spec.threshold is None:
        return False
    tolerance = max(500.0, topic_spec.threshold * 0.05)
    return abs(topic_spec.threshold - evidence_spec.threshold) <= tolerance


def _social_crypto_threshold_market_context_ok(title: str, tokens: set[str]) -> bool:
    topic_spec = _threshold_spec(title)
    if topic_spec.threshold is None:
        return True
    if tokens & {"flow", "flows", "liquidity", "exchange", "exchanges", "repricing"}:
        return True
    if "spot" in tokens and tokens & {"price", "prices", "support", "resistance", "volume", "momentum", "breakout"}:
        return True
    if tokens & {"etf", "etfs"} and tokens & {"flow", "flows", "liquidity", "repricing"}:
        return True
    return False


def _social_noise_tokens(tokens: set[str]) -> bool:
    return bool(tokens & _SOCIAL_PROMO_TOKENS)


def _allow_macro_evidence(title: str, text: str, source_context: str = "") -> bool:
    combined = f"{text} {source_context}".strip()
    lowered = combined.lower()
    tokens = _tokenize(combined)
    title_tokens = _topic_tokens(title)
    overlap = len((title_tokens - {"june", "april", "may"}) & tokens)
    if any(phrase in lowered for phrase in _MACRO_LOW_SIGNAL_PHRASES):
        return False
    if "breaking" in tokens and _looks_like_alert_spam(combined):
        return False
    if MACRO_BAD_CONTEXT_TERMS & tokens:
        return False
    if not (tokens & MACRO_SIGNAL_TERMS):
        return False
    if overlap < 1 and not (tokens & {"fed", "fomc", "powell"}):
        return False
    if not ((tokens & MACRO_STRONG_TERMS) or (tokens & _MACRO_STRONG_CONTEXT_TERMS)):
        return False
    return True


def _allow_crypto_evidence(title: str, text: str, source_context: str = "") -> bool:
    combined = f"{text} {source_context}".strip()
    lowered = combined.lower()
    tokens = _tokenize(combined)
    topic_tokens = _tokenize(title)
    topic_entities = topic_tokens & _CRYPTO_ENTITY_TOKENS
    topic_spec = _threshold_spec(title)
    evidence_spec = _threshold_spec(text)
    if topic_entities and not (topic_entities & tokens):
        return False
    if any(phrase in lowered for phrase in _CRYPTO_LOW_SIGNAL_PHRASES):
        return False
    if {"poll", "vote"} & tokens:
        return False
    if "predictions" in tokens and not (tokens & {"spot", "etf", "flows", "flow", "exchange", "liquidity"}):
        return False
    if "breaking" in tokens and _looks_like_alert_spam(combined):
        return False
    if not (tokens & _CRYPTO_ENTITY_TOKENS):
        return False
    if not ((tokens & _CRYPTO_STRONG_SIGNAL_TERMS) or ("spot" in tokens and "price" in tokens)):
        return False
    if topic_spec.threshold is not None and evidence_spec.threshold is not None:
        tolerance = max(500.0, topic_spec.threshold * 0.05)
        if abs(topic_spec.threshold - evidence_spec.threshold) > tolerance:
            return False
    if topic_spec.window and evidence_spec.window and topic_spec.window != evidence_spec.window:
        return False
    return True


def _threshold_entity(text: str) -> Optional[str]:
    tokens = _tokenize(text)
    for entity, aliases in _CRYPTO_ENTITY_ALIASES.items():
        if tokens & aliases:
            return entity
    return None


def _threshold_direction(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if re.search(r"\b(range|between)\b", lowered):
        return "range"
    if re.search(r"\b(above|over|exceed|exceeds|exceeding|greater than|at least|reach|reaches|hit|hits)\b", lowered):
        return "above"
    if re.search(r"\b(below|under|less than|at most)\b", lowered):
        return "below"
    return None


def _parse_threshold_number(raw: str, suffix: str = "") -> Optional[float]:
    cleaned = raw.replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    suffix = suffix.lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    return value


def _threshold_numbers(text: str) -> list[float]:
    lowered = (text or "").lower()
    values: list[float] = []
    patterns = [
        r"(?<![a-z0-9])\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s*([km])?(?![a-z0-9])",
        r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*([km])(?![a-z0-9])",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, lowered):
            value = _parse_threshold_number(match.group(1), match.group(2) or "")
            if value is None:
                continue
            # Ignore years and tiny incidental numbers unless explicitly scaled.
            if not match.group(2) and 1900 <= value <= 2100:
                continue
            if value < 10:
                continue
            if value not in values:
                values.append(value)
    return values


def _threshold_window(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if "this week" in lowered or "by end of week" in lowered:
        return "this_week"
    if "this month" in lowered or "end of month" in lowered:
        return "this_month"
    if "this year" in lowered or "end of year" in lowered:
        return "this_year"
    match = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{1,2})\b",
        lowered,
    )
    if match:
        month = match.group(1)[:3]
        return f"{month}-{int(match.group(2)):02d}"
    return None


def _threshold_spec(text: str) -> _ThresholdSpec:
    numbers = _threshold_numbers(text)
    return _ThresholdSpec(
        entity=_threshold_entity(text),
        direction=_threshold_direction(text),
        threshold=max(numbers) if numbers else None,
        window=_threshold_window(text),
    )


def _date_refs(text: str, default_year: Optional[int] = None) -> set[str]:
    refs: set[str] = set()
    lowered = (text or "").lower()
    for match in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", lowered):
        refs.add(f"{match.group(1)}-{match.group(2)}-{match.group(3)}")
    compact_pattern = "|".join(sorted({key for key in _MONTH_NUMBERS if len(key) == 3}, key=len, reverse=True))
    compact_date_pattern = rf"(?<!\d)(\d{{2}})({compact_pattern})(\d{{2}})(?!\d)"
    for match in re.finditer(compact_date_pattern, lowered):
        year = 2000 + int(match.group(1))
        month = _MONTH_NUMBERS[match.group(2)]
        day = int(match.group(3))
        if 1 <= day <= 31:
            refs.add(f"{year:04d}-{month:02d}-{day:02d}")
    month_pattern = "|".join(sorted(_MONTH_NUMBERS, key=len, reverse=True))
    pattern = rf"\b({month_pattern})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}))?\b"
    for match in re.finditer(pattern, lowered):
        month = _MONTH_NUMBERS[match.group(1).rstrip(".")]
        day = int(match.group(2))
        if not 1 <= day <= 31:
            continue
        if match.group(3):
            refs.add(f"{int(match.group(3)):04d}-{month:02d}-{day:02d}")
        elif default_year:
            refs.add(f"{default_year:04d}-{month:02d}-{day:02d}")
        else:
            refs.add(f"{month:02d}-{day:02d}")
    return refs


def _report_base_date(report: schema.Report) -> Optional[datetime.date]:
    for value in (report.generated_at, report.range_to, report.range_from):
        if not value:
            continue
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except ValueError:
            continue
    return None


def _sports_target_date(report: schema.Report) -> Optional[str]:
    for note in report.planning_notes:
        match = re.search(r"\bnba-slate-date:(20\d{2}-\d{2}-\d{2})\b", str(note))
        if match:
            return match.group(1)
    base = _report_base_date(report)
    refs = _date_refs(report.topic, default_year=base.year if base else None)
    full_refs = sorted(ref for ref in refs if re.match(r"^20\d{2}-\d{2}-\d{2}$", ref))
    if full_refs:
        return full_refs[0]
    topic_lower = report.topic.lower()
    if base and ("tomorrow" in topic_lower or "tomorrows" in topic_lower):
        return (base + timedelta(days=1)).isoformat()
    if base and ("today" in topic_lower or "tonight" in topic_lower):
        return base.isoformat()
    return None


def _sports_market_date_compatible(item, target_date: Optional[str]) -> bool:
    if not target_date:
        return True
    market_text = " ".join(
        str(part) for part in (
            getattr(item, "title", ""),
            getattr(item, "question", ""),
            getattr(item, "url", ""),
            getattr(item, "ticker", ""),
            getattr(item, "event_ticker", ""),
            getattr(item, "end_date", ""),
            getattr(item, "end_datetime", ""),
        ) if part
    )
    refs = _date_refs(market_text)
    if not refs:
        return True
    try:
        target = datetime.fromisoformat(target_date).date()
        allowed = {target.isoformat(), (target + timedelta(days=1)).isoformat(), target.strftime("%m-%d")}
    except ValueError:
        allowed = {target_date, target_date[5:]}
    return bool(refs & allowed)


def _sports_evidence_date_compatible(text: str, target_date: Optional[str]) -> bool:
    if not target_date:
        return True
    refs = _date_refs(text)
    if not refs:
        return True
    try:
        target = datetime.fromisoformat(target_date).date()
        allowed = {target.isoformat(), target.strftime("%m-%d")}
    except ValueError:
        allowed = {target_date, target_date[5:]}
    return bool(refs & allowed)


def _threshold_market_compatible(topic: str, item) -> bool:
    """Reject forecast anchors that represent a different numeric contract.

    This is intentionally conservative. Watchlists can still surface adjacent
    threshold markets, but forecast anchoring should not blend or lead with a
    market that answers a different threshold question.
    """
    topic_spec = _threshold_spec(topic)
    if topic_spec.threshold is None and topic_spec.direction is None:
        return True

    market_text = " ".join(
        part for part in (
            getattr(item, "title", ""),
            getattr(item, "question", ""),
            getattr(item, "ticker", ""),
            getattr(item, "event_ticker", ""),
            getattr(item, "series_ticker", ""),
        ) if part
    )
    market_spec = _threshold_spec(market_text)
    market_type = getattr(item, "market_type", "unknown")
    looks_threshold_like = market_type == "threshold" or market_spec.threshold is not None or market_spec.direction in {"above", "below", "range"}
    topic_tokens = _tokenize(topic)
    market_tokens = _tokenize(market_text)
    if (
        topic_spec.threshold is None
        and topic_tokens & {"fed", "fomc", "powell", "cut", "cuts", "hike", "hikes"}
        and looks_threshold_like
        and not (market_tokens & {"cut", "cuts", "hike", "hikes"})
    ):
        return False

    if topic_spec.threshold is not None and looks_threshold_like and market_spec.threshold is None:
        return False
    if topic_spec.entity and market_spec.entity and topic_spec.entity != market_spec.entity:
        return False
    if topic_spec.direction and market_spec.direction and topic_spec.direction != market_spec.direction:
        return False
    if topic_spec.threshold is not None and market_spec.threshold is not None:
        tolerance = max(500.0, topic_spec.threshold * 0.05)
        if abs(topic_spec.threshold - market_spec.threshold) > tolerance:
            return False
    if topic_spec.window and market_spec.window:
        if topic_spec.window != market_spec.window and topic_spec.window not in {"this_week", "this_month", "this_year"}:
            return False
        if topic_spec.window == "this_week" and market_spec.window == "this_year":
            return False
        if topic_spec.window == "this_month" and market_spec.window == "this_year":
            return False
    return True


def _month_match_score(topic: str, market_text: str) -> int:
    topic_months = _tokenize(topic) & _MONTH_TOKENS
    if not topic_months:
        return 0
    market_months = _tokenize(market_text) & _MONTH_TOKENS
    if topic_months & market_months:
        return 2
    if market_months:
        return -3
    return -1


def _macro_market_allowed(topic: str, market_text: str) -> bool:
    topic_tokens = _tokenize(topic)
    market_tokens = _tokenize(market_text)
    if "fed" in topic_tokens and "ecb" in market_tokens and "fed" not in market_tokens:
        return False
    if "ecb" in topic_tokens and "fed" in market_tokens and "ecb" not in market_tokens:
        return False
    if (topic_tokens & {"fed", "fomc", "powell"}) and not (market_tokens & {"fed", "fomc", "powell"}):
        return False
    if topic_tokens & {"cut", "cuts", "hike", "hikes"}:
        if not (market_tokens & {"cut", "cuts", "hike", "hikes"}):
            return False
    if topic_tokens & {"cpi", "inflation"}:
        if not (market_tokens & {"cpi", "inflation"}):
            return False
    if topic_tokens & {"jobs", "job", "payroll", "payrolls"}:
        if not (market_tokens & {"jobs", "job", "payroll", "payrolls"}):
            return False
    topic_core = _topic_tokens(topic) - _MONTH_TOKENS - {"meeting", "meetings"}
    market_core = market_tokens - _MONTH_TOKENS - {"meeting", "meetings", "interest"}
    if topic_core & {"fed", "fomc", "powell", "rates", "rate", "cut", "cuts", "hike", "hikes"}:
        return len(topic_core & market_core) >= 2
    return True


def _filter_date_specific_macro_markets(topic: str, items: list) -> list:
    topic_months = _tokenize(topic) & _MONTH_TOKENS
    if not topic_months:
        return items
    matching = [
        item for item in items
        if topic_months & (_tokenize(f"{getattr(item, 'title', '')} {getattr(item, 'question', '')}") & _MONTH_TOKENS)
    ]
    return matching


def _is_sports_query(text: str) -> bool:
    text_lower = (text or "").lower()
    matchup = _matchup_signature(text_lower)
    sports_terms = {"nba", "nfl", "nhl", "mlb", "wnba", "basketball", "football", "soccer", "baseball", "game", "games"}
    return bool(matchup or (SPORTS_TEAM_TOKENS & _tokenize(text_lower)) or any(term in text_lower for term in sports_terms))


def _is_esports_query(text: str) -> bool:
    return eq.is_esports_query(text)


def _is_esports_match_query(text: str) -> bool:
    lowered = (text or "").lower()
    if not _is_esports_query(text):
        return False
    if any(term in lowered for term in ("map pool", "major winner", "tournament winner", "champion", "props", "kills", "handicap", "total maps")):
        return False
    return bool(_matchup_signature(lowered) or any(term in lowered for term in ("match", "matches", "game", "games", "today", "tonight", "tomorrow")))


def _is_esports_player_prop_query(text: str) -> bool:
    """Thin wrapper around eq.is_esports_player_prop_query for forecast-internal use.

    Disjoint from _is_esports_match_query: player-prop queries name a pro handle
    or pair an eSports domain term with a player-level stat marker
    (kills/ADR/headshots/etc.). v1.0.55 ships detection only; surfacing wiring
    lands in v1.0.56.
    """
    return eq.is_esports_player_prop_query(text)


def _is_weather_query(text: str) -> bool:
    return eq.is_weather_query(text)


def _is_macro_query(text: str) -> bool:
    return eq.is_macro_query(text)


def _favorite_tokens(favorite_label: str) -> set[str]:
    return {
        token for token in _tokenize(favorite_label)
        if token not in {"yes", "no", "favorite"} and len(token) > 2
    }


def _sports_candidate_score(
    text: str,
    title: str,
    source: str,
    base_score: float,
    author: str = "",
    community: str = "",
    exact_date_match: bool = False,
) -> Optional[_EvidenceCandidate]:
    source_context = f"{author} {community}".strip()
    tokens = _tokenize(f"{text} {source_context}")
    if "check" in tokens and "out" in tokens:
        tokens.discard("out")
    title_tokens = _topic_tokens(title)
    sides = _matchup_side_tokens(title)
    overlap = len(title_tokens & tokens)
    team_hits = sum(1 for side in sides if side & tokens) if sides else 0
    exact_match = bool(team_hits == len(sides) and sides)
    category = eq.classify_sports_evidence(
        text,
        source_context,
        exact_match=exact_match,
        exact_date=exact_date_match,
        allow_market_context=True,
    )
    if category not in {"high_signal", "market_context"}:
        return None
    strict_status_terms = {
        "injury", "injuries", "injured", "ruled", "questionable", "doubtful",
        "probable", "available", "inactive", "scratch", "scratched", "status",
        "report", "listed",
    }
    strict_rest_terms = {
        "rest", "resting", "minutes", "restriction", "restricted", "back-to-back", "b2b",
    }
    strict_lineup_terms = {"lineup", "lineups", "starter", "starters", "starting", "confirmed", "announced", "expected"}
    strict_incentive_terms = {
        "elimination", "eliminated", "clinch", "clinched", "tank", "tanking",
    }
    line_movement_terms = {"movement", "moved", "steam", "shift", "shifted", "shortened", "drifted"}

    has_status = bool(tokens & strict_status_terms)
    has_rest = bool(tokens & strict_rest_terms)
    has_lineup = bool(tokens & {"lineup", "lineups", "starter", "starters", "starting"} and tokens & {"confirmed", "announced", "expected", "available", "inactive", "ruled", "questionable", "doubtful"})
    has_incentive = bool(tokens & strict_incentive_terms)
    if {"playoff", "playoffs"} & tokens and tokens & {"elimination", "eliminated", "clinch", "clinched"}:
        has_incentive = True
    if "must" in tokens and "win" in tokens and (
        tokens & {"elimination", "eliminated", "clinch", "clinched"}
    ):
        has_incentive = True
    has_actionable_signal = has_status or has_rest or has_lineup or has_incentive
    has_clean_market_context = bool(tokens & SPORTS_MARKET_CONTEXT_TERMS and tokens & line_movement_terms)
    if category == "high_signal" and not has_actionable_signal:
        return None
    if category == "market_context" and not has_clean_market_context:
        return None

    concrete_hits = int(has_status) + int(has_rest) + int(has_lineup) + int(has_incentive)
    if category == "market_context":
        concrete_hits = max(concrete_hits, 1)
    if not sides and "nba" in title.lower() and not ((eq.NBA_TEAM_TOKENS & tokens) or "nba" in tokens):
        return None
    if sides and team_hits == 0:
        return None
    if team_hits < len(sides):
        return None
    if overlap == 0:
        return None

    score = min(base_score, 80) * 0.25 + overlap * 5 + concrete_hits * 5
    if team_hits == len(sides) and sides:
        score += 12
    elif team_hits:
        score += 4

    if concrete_hits:
        score += 12
    if has_status or has_rest or has_lineup:
        score += 10
    if has_incentive:
        score += 6
    if SPORTS_MARKET_CONTEXT_TERMS & tokens and concrete_hits:
        score += 4
    if SPORTS_REPORTER_TOKENS & _tokenize(f"{author} {community}"):
        score += 8

    if SPORTS_LOW_SIGNAL_TERMS & tokens:
        score -= 18
        if not concrete_hits:
            score -= 18
    if SPORTS_RECAP_TERMS & tokens and not concrete_hits:
        score -= 14
    mentioned_teams = len(SPORTS_TEAM_TOKENS & tokens)
    if mentioned_teams >= 4:
        return None
    if mentioned_teams >= 3 and not SPORTS_HIGH_SIGNAL_TERMS & tokens:
        score -= 10
    if score < 22:
        return None

    return _EvidenceCandidate(
        score=score,
        text=text.strip(),
        tokens=tokens,
        source=source,
        team_hits=team_hits,
        signal_hits=concrete_hits,
    )


def _esports_candidate_score(
    text: str,
    title: str,
    source: str,
    base_score: float,
    author: str = "",
    community: str = "",
) -> Optional[_EvidenceCandidate]:
    source_context = f"{author} {community}".strip()
    context = f"{text} {source_context}".strip()
    lowered = context.lower()
    tokens = _tokenize(context)
    title_tokens = _topic_tokens(title)
    sides = _matchup_side_tokens(title)
    overlap = len(title_tokens & tokens)
    team_hits = sum(1 for side in sides if side & tokens) if sides else 0
    exact_match = bool(team_hits == len(sides) and sides)

    low_signal_phrases = (
        "line feels too low",
        "streak starter",
        "sign up and deposit",
        "whale movements",
        "odds favor",
        "price gap",
        "safe to say",
        "pre cash",
    )
    low_signal_terms = {
        "animgraph", "down", "downdetector", "hours", "funny", "free", "favorite", "thanks",
        "status", "reported", "players", "install", "download",
    }
    if any(phrase in lowered for phrase in low_signal_phrases):
        return None
    if text.strip().startswith("@"):
        return None
    if tokens & low_signal_terms and not (tokens & {"patch", "update", "roster", "standin", "stand-in", "sub", "substitute", "veto", "map", "pool", "qualifier", "playoff", "playoffs", "bracket", "lan"}):
        return None
    if not eq.is_esports_rationale_evidence(text, source_context, exact_match=exact_match, topic=title):
        return None
    if eq.is_cs2_query(title) and not eq.is_cs2_market_text(context):
        return None
    if sides:
        if team_hits < len(sides):
            return None
    elif overlap == 0:
        return None

    signal_hits = len(eq.ESPORTS_HIGH_SIGNAL_TERMS & tokens)
    score = min(base_score, 78) * 0.25 + overlap * 5 + signal_hits * 4
    if exact_match:
        score += 10
    if signal_hits:
        score += 8
    if {"roster", "standin", "stand-in", "sub", "substitute", "coach", "bench", "benched"} & tokens:
        score += 10
    if {"patch", "update", "map", "pool", "veto"} & tokens:
        score += 8
    if {"qualifier", "qualifiers", "playoff", "playoffs", "bracket", "elimination", "seed", "seeding", "lan"} & tokens:
        score += 6
    if eq.ESPORTS_LOW_SIGNAL_TERMS & tokens:
        score -= 18
    if score < 22:
        return None

    return _EvidenceCandidate(
        score=score,
        text=text.strip(),
        tokens=tokens,
        source=source,
        team_hits=team_hits,
        signal_hits=signal_hits,
    )


def _generic_candidate_score(
    text: str,
    title: str,
    base_score: float,
    weather_query: bool = False,
    macro_query: bool = False,
    source_context: str = "",
    source: str = "generic",
) -> Optional[_EvidenceCandidate]:
    context = f"{text} {source_context}".strip()
    tokens = _tokenize(context)
    title_tokens = _topic_tokens(title)
    overlap = len(title_tokens & tokens)
    crypto_query = _is_crypto_query(title)
    source_name = _source_kind(source)

    if overlap == 0:
        return None

    if weather_query:
        location_tokens = title_tokens - WEATHER_WEAK_TERMS - {"tomorrow", "today", "tonight"}
        if not (WEATHER_SIGNAL_TERMS & tokens):
            return None
        if location_tokens and not (location_tokens & tokens):
            return None
        if overlap < 2 and not (WEATHER_SIGNAL_TERMS & tokens):
            return None

    if macro_query:
        macro_overlap = len((title_tokens - {"will", "have", "us", "usa", "by", "in", "end", "next", "month", "year"}) & tokens)
        signal_hits = len(MACRO_SIGNAL_TERMS & tokens)
        strong_hits = len(MACRO_STRONG_TERMS & tokens)
        if MACRO_BAD_CONTEXT_TERMS & tokens:
            return None
        if signal_hits == 0:
            return None
        if strong_hits == 0 and macro_overlap < 2:
            return None
        if signal_hits < 2 and not (MACRO_CONTEXT_TERMS & tokens and macro_overlap >= 1):
            return None
        if not ((MACRO_STRONG_TERMS & tokens) or (MACRO_SUPPORT_TERMS & tokens and macro_overlap >= 1)):
            return None
        if "recession" in title_tokens and "recession" in tokens and not (RECESSION_SUPPORT_TERMS & tokens):
            return None
        if not _allow_macro_evidence(title, text, source_context):
            return None
        if source_name in _SOCIAL_SOURCES:
            if _social_noise_tokens(tokens):
                return None
            if not _social_macro_context_ok(tokens, title_tokens):
                return None

    if crypto_query:
        if not _allow_crypto_evidence(title, text, source_context):
            return None
        if source_name in _SOCIAL_SOURCES:
            if _social_noise_tokens(tokens):
                return None
            if not _social_crypto_context_ok(tokens, title_tokens):
                return None

    if LOW_SIGNAL_SOCIAL_TERMS & tokens and not DRIVER_TERMS & tokens:
        return None
    if source_name in _SOCIAL_SOURCES and _social_noise_tokens(tokens) and not ((tokens & MACRO_SIGNAL_TERMS) or (tokens & _CRYPTO_STRONG_SIGNAL_TERMS)):
        return None
    if overlap < 2 and not DRIVER_TERMS & tokens:
        return None

    score = base_score + overlap * 4 + _source_context_bonus(source_name, source_context)
    if DRIVER_TERMS & tokens:
        score += 8
    if weather_query and WEATHER_SIGNAL_TERMS & tokens:
        score += 10
    if macro_query:
        score += len(MACRO_SIGNAL_TERMS & tokens) * 4
        if MACRO_STRONG_TERMS & tokens:
            score += 8
        if source_name not in _SOCIAL_SOURCES:
            score += 6
    if crypto_query:
        score += len(_CRYPTO_STRONG_SIGNAL_TERMS & tokens) * 3
        if source_name not in _SOCIAL_SOURCES:
            score += 4
    return _EvidenceCandidate(
        score=score,
        text=text.strip(),
        tokens=tokens,
        source=source_name or "generic",
        team_hits=0,
        signal_hits=len(DRIVER_TERMS & tokens),
    )


def _degraded_source_item_score(item, source: str, topic: str) -> float:
    text = getattr(item, "text", "") or getattr(item, "title", "") or getattr(item, "snippet", "") or ""
    context = getattr(item, "author_handle", "") or getattr(item, "subreddit", "") or getattr(item, "source_domain", "")
    base_score = float(getattr(item, "score", 0) or 0)
    macro_query = _is_macro_query(topic)
    crypto_query = _is_crypto_query(topic)
    candidate = _generic_candidate_score(
        text,
        topic,
        base_score,
        macro_query=macro_query,
        source_context=context,
        source=source,
    )
    if candidate:
        if macro_query and source in _SOCIAL_SOURCES:
            return 180.0 + candidate.score
        if crypto_query and source in _SOCIAL_SOURCES:
            return 420.0 + candidate.score
        return 1_000.0 + candidate.score
    tokens = _tokenize(f"{text} {context}")
    overlap = len(_topic_tokens(topic) & tokens)
    penalty = 120.0 if source in _SOCIAL_SOURCES else 40.0
    return base_score + overlap - penalty


def _degraded_source_penalty_reason(item, source: str, topic: str) -> Optional[str]:
    text = getattr(item, "text", "") or getattr(item, "title", "") or getattr(item, "snippet", "") or ""
    context = getattr(item, "author_handle", "") or getattr(item, "subreddit", "") or getattr(item, "source_domain", "")
    tokens = _tokenize(f"{text} {context}")
    topic_tokens = _topic_tokens(topic)
    overlap = len(topic_tokens & tokens)
    macro_query = _is_macro_query(topic)
    crypto_query = _is_crypto_query(topic)
    if macro_query and source in _SOCIAL_SOURCES:
        if _social_noise_tokens(tokens) or not _social_macro_context_ok(tokens, topic_tokens) or not _macro_social_lead_ok(tokens):
            return "macro_social_demoted"
    if crypto_query and source in _SOCIAL_SOURCES:
        if (
            _social_noise_tokens(tokens)
            or not _social_crypto_context_ok(tokens, topic_tokens)
            or not _social_crypto_threshold_match_ok(topic, text)
            or not _social_crypto_threshold_market_context_ok(topic, tokens)
            or not (tokens & _CRYPTO_STRONG_SIGNAL_TERMS)
        ):
            return "crypto_opinion_demoted"
    if overlap >= 1:
        return "source_row_suppressed"
    return None


def _rerank_degraded_source_items(report: schema.Report, topic: str) -> None:
    if not (_is_macro_query(topic) or _is_crypto_query(topic)):
        return
    for source_name, items in (("x", report.x), ("reddit", report.reddit), ("web", report.web)):
        scored = []
        for item in items:
            reason = _degraded_source_penalty_reason(item, source_name, topic)
            if reason:
                _bump_debug_counter(report, reason)
                _bump_debug_counter(report, "source_row_suppressed")
            scored.append((_degraded_source_item_score(item, source_name, topic), item))
        items[:] = [item for _, item in sorted(scored, key=lambda row: row[0], reverse=True)]


def _bump_debug_counter(report: schema.Report, key: str, amount: int = 1) -> None:
    debug = report.evidence_fusion_stats.setdefault("debug_counters", {})
    debug[key] = int(debug.get(key, 0) or 0) + amount


def _collect_evidence_candidates(report: schema.Report, title: str) -> list[_EvidenceCandidate]:
    title_lower = title.lower()
    sports_query = _is_sports_query(title) or _is_sports_query(report.topic)
    esports_query = _is_esports_query(title) or _is_esports_query(report.topic)
    weather_query = _is_weather_query(title) or _is_weather_query(report.topic)
    macro_query = _is_macro_query(title) or _is_macro_query(report.topic)
    debug_domain = "crypto" if _is_crypto_query(title) else "macro" if macro_query else ""
    candidates: list[_EvidenceCandidate] = []

    fused = evidence_fusion.fuse_evidence(report, title, "prediction", limit=4)
    if fused.candidate_count:
        report.evidence_fusion_stats["candidate_count"] = max(
            int(report.evidence_fusion_stats.get("candidate_count", 0) or 0),
            fused.candidate_count,
        )
        report.evidence_fusion_stats["driver_count"] = max(
            int(report.evidence_fusion_stats.get("driver_count", 0) or 0),
            len(fused.drivers),
        )
        report.evidence_fusion_stats["cluster_count"] = max(
            int(report.evidence_fusion_stats.get("cluster_count", 0) or 0),
            fused.cluster_count,
        )
    title_sides = _matchup_side_tokens(title)
    sports_target_date = _sports_target_date(report) if (sports_query or esports_query) else None
    for driver in fused.drivers:
        exact_date_match = _sports_evidence_date_compatible(driver.text, sports_target_date)
        if (sports_query or esports_query) and not exact_date_match:
            continue
        tokens = _tokenize(driver.text)
        team_hits = sum(1 for side in title_sides if side & tokens) if title_sides else 0
        signal_hits = len((DRIVER_TERMS | SPORTS_HIGH_SIGNAL_TERMS | WEATHER_SIGNAL_TERMS | MACRO_SIGNAL_TERMS) & tokens)
        if esports_query:
            candidate = _esports_candidate_score(
                driver.text,
                title,
                driver.source,
                driver.score * 100.0,
            )
            if not candidate:
                continue
            candidates.append(candidate)
            continue
        if sports_query:
            candidate = _sports_candidate_score(
                driver.text,
                title,
                driver.source,
                driver.score * 100.0,
                exact_date_match=exact_date_match,
            )
            if not candidate:
                continue
            candidates.append(candidate)
            continue
        candidate = _generic_candidate_score(
            driver.text,
            title,
            driver.score * 100.0,
            weather_query=weather_query,
            macro_query=macro_query,
            source=driver.source,
        )
        if candidate:
            candidates.append(
                _EvidenceCandidate(
                    score=max(candidate.score, driver.score * 100.0),
                    text=driver.text,
                    tokens=tokens,
                    source=driver.source,
                    team_hits=team_hits,
                    signal_hits=signal_hits,
                )
            )
        elif debug_domain and len(_topic_tokens(title) & tokens) >= 1:
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{debug_domain}")

    for item in report.x[:12]:
        text = getattr(item, "text", "") or ""
        if not text:
            continue
        exact_date_match = _sports_evidence_date_compatible(text, sports_target_date)
        if (sports_query or esports_query) and not exact_date_match:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _esports_candidate_score(
                text,
                title,
                "x",
                base_score,
                author=getattr(item, "author_handle", ""),
            )
            if esports_query
            else _sports_candidate_score(
                text,
                title,
                "x",
                base_score,
                author=getattr(item, "author_handle", ""),
                exact_date_match=exact_date_match,
            )
            if sports_query
            else _generic_candidate_score(
                text,
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "author_handle", ""),
                source="x",
            )
        )
        if candidate:
            candidates.append(candidate)
        elif debug_domain and len(_topic_tokens(title) & _tokenize(text)) >= 1:
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{debug_domain}")

    for item in report.reddit[:10]:
        text = getattr(item, "title", "") or ""
        if not text:
            continue
        exact_date_match = _sports_evidence_date_compatible(text, sports_target_date)
        if (sports_query or esports_query) and not exact_date_match:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _esports_candidate_score(
                text,
                title,
                "reddit",
                base_score,
                community=getattr(item, "subreddit", ""),
            )
            if esports_query
            else _sports_candidate_score(
                text,
                title,
                "reddit",
                base_score,
                community=getattr(item, "subreddit", ""),
                exact_date_match=exact_date_match,
            )
            if sports_query
            else _generic_candidate_score(
                f"{text} {getattr(item, 'subreddit', '')}",
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "subreddit", ""),
                source="reddit",
            )
        )
        if candidate:
            candidates.append(candidate)
        elif debug_domain and len(_topic_tokens(title) & _tokenize(text)) >= 1:
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{debug_domain}")

    for item in report.web[:8]:
        text = f"{getattr(item, 'title', '')} {getattr(item, 'snippet', '')}".strip()
        if not text:
            continue
        exact_date_match = _sports_evidence_date_compatible(text, sports_target_date)
        if (sports_query or esports_query) and not exact_date_match:
            continue
        base_score = getattr(item, "score", 0)
        candidate = (
            _esports_candidate_score(
                text,
                title,
                "web",
                base_score,
                community=getattr(item, "source_domain", ""),
            )
            if esports_query
            else _sports_candidate_score(
                text,
                title,
                "web",
                base_score,
                community=getattr(item, "source_domain", ""),
                exact_date_match=exact_date_match,
            )
            if sports_query
            else _generic_candidate_score(
                text,
                title,
                base_score,
                weather_query=weather_query,
                macro_query=macro_query,
                source_context=getattr(item, "source_domain", ""),
                source="web",
            )
        )
        if candidate:
            candidates.append(candidate)
        elif debug_domain and len(_topic_tokens(title) & _tokenize(text)) >= 1:
            _bump_debug_counter(report, f"rejected_low_signal_evidence:{debug_domain}")

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def _polymarket_match_score(topic: str, item: schema.PolymarketItem) -> tuple[int, int, int, float]:
    topic_signature = _matchup_signature(topic)
    market_text = f"{item.title} {item.question}"
    item_signature = _matchup_signature(item.title or item.question)
    signature_match = int(bool(topic_signature and topic_signature == item_signature))
    tokens = _topic_tokens(topic)
    market_tokens = _tokenize(market_text)
    overlap = len(tokens & market_tokens)
    return signature_match, _month_match_score(topic, market_text), overlap, item.relevance


def _best_polymarket(topic: str, items: list[schema.PolymarketItem], sports_target_date: Optional[str] = None, allow_esports_prop: bool = False) -> Optional[schema.PolymarketItem]:
    if not items:
        return None
    items = [item for item in items if _threshold_market_compatible(topic, item)]
    if not items:
        return None
    topic_esports_subdomain = eq.esports_subdomain_of(topic)
    if _is_esports_match_query(topic) and topic_esports_subdomain:
        items = [
            item for item in items
            if eq.esports_subdomain_of(f"{item.title} {item.question} {item.url}") == topic_esports_subdomain
        ]
        if not items:
            return None
    if _is_sports_query(topic) or _is_esports_match_query(topic):
        items = [
            item for item in items
            if _is_direct_game_market(item, allow_esports_prop=allow_esports_prop)
            and _sports_market_date_compatible(item, sports_target_date)
            and (_is_sports_query(topic) or _is_esports_market_item(item))
        ]
        if not items:
            return None
    if _is_macro_query(topic):
        items = [
            item for item in items
            if _macro_market_allowed(topic, f"{item.title} {item.question}")
        ]
        items = _filter_date_specific_macro_markets(topic, items)
        if not items:
            return None
    ranked = sorted(items, key=lambda item: (_polymarket_match_score(topic, item), item.score), reverse=True)
    return ranked[0]


def _best_kalshi(topic: str, items: list[schema.KalshiItem], sports_target_date: Optional[str] = None, allow_esports_prop: bool = False) -> Optional[schema.KalshiItem]:
    if not items:
        return None
    items = [item for item in items if _threshold_market_compatible(topic, item)]
    if not items:
        return None
    topic_esports_subdomain = eq.esports_subdomain_of(topic)
    if _is_esports_match_query(topic) and topic_esports_subdomain:
        items = [
            item for item in items
            if eq.esports_subdomain_of(f"{item.title} {item.question} {item.url}") == topic_esports_subdomain
        ]
        if not items:
            return None
    if _is_sports_query(topic) or _is_esports_match_query(topic):
        items = [
            item for item in items
            if _is_direct_game_market(item, allow_esports_prop=allow_esports_prop)
            and _sports_market_date_compatible(item, sports_target_date)
            and (_is_sports_query(topic) or _is_esports_market_item(item))
        ]
        if not items:
            return None
    if _is_macro_query(topic):
        items = [
            item for item in items
            if _macro_market_allowed(topic, f"{item.title} {item.question}")
        ]
        items = _filter_date_specific_macro_markets(topic, items)
        if not items:
            return None
    topic_signature = _matchup_signature(topic)
    if topic_signature:
        matching = [
            item for item in items
            if _item_matchup_signature(item) == topic_signature
        ]
        if matching:
            return max(matching, key=lambda item: item.score)
    ranked = sorted(
        items,
        key=lambda item: (
            _month_match_score(topic, f"{item.title} {item.question}"),
            len(_topic_tokens(topic) & _tokenize(f"{item.title} {item.question}")),
            item.score,
        ),
        reverse=True,
    )
    return ranked[0]


def _matching_kalshi_for_polymarket(
    poly_item: schema.PolymarketItem,
    kalshi_items: list[schema.KalshiItem],
    sports_target_date: Optional[str] = None,
    allow_esports_prop: bool = False,
) -> Optional[schema.KalshiItem]:
    kalshi_items = [item for item in kalshi_items if _threshold_market_compatible(f"{poly_item.title} {poly_item.question}", item)]
    signature = _item_matchup_signature(poly_item)
    if signature:
        for item in kalshi_items:
            if (
                _is_direct_game_market(item, allow_esports_prop=allow_esports_prop)
                and _sports_market_date_compatible(item, sports_target_date)
                and _item_matchup_signature(item) == signature
            ):
                return item
    poly_spec = _threshold_spec(f"{poly_item.title} {poly_item.question}")
    if poly_spec.threshold is not None or poly_spec.direction is not None:
        for item in kalshi_items:
            if _threshold_market_compatible(f"{poly_item.title} {poly_item.question}", item):
                return item
    return None


def _is_nba_market_item(item: schema.PolymarketItem | schema.KalshiItem) -> bool:
    text = f"{getattr(item, 'title', '')} {getattr(item, 'question', '')} {getattr(item, 'url', '')}"
    return eq.is_nba_market_text(text)


def _is_esports_market_item(item: schema.PolymarketItem | schema.KalshiItem) -> bool:
    text = f"{getattr(item, 'title', '')} {getattr(item, 'question', '')} {getattr(item, 'url', '')}"
    item_type = getattr(item, "market_type", "unknown")
    if item_type in {"game_outcome", "esports_prop", "esports_title"} and eq.is_esports_query(text):
        return True
    return item_type == "unknown" and eq.is_esports_query(text) and _is_direct_game_market(item)


def _is_direct_game_market(item: schema.PolymarketItem | schema.KalshiItem, allow_esports_prop: bool = False) -> bool:
    item_type = getattr(item, "market_type", "unknown")
    if item_type == "game_outcome":
        return True
    if allow_esports_prop and item_type == "esports_prop":
        return True
    if item_type != "unknown":
        return False
    return market_types.is_direct_game_outcome(
        getattr(item, "title", ""),
        getattr(item, "question", ""),
        getattr(item, "url", ""),
    )


def _top_evidence(report: schema.Report, title: str, limit: int = 2) -> list[str]:
    candidates = _collect_evidence_candidates(report, title)
    results = []
    seen = set()
    for candidate in candidates:
        text = candidate.text
        if not text:
            continue
        short = text.replace("\n", " ")[:180].strip()
        if short in seen:
            continue
        seen.add(short)
        results.append(short + ("..." if len(text) > 180 else ""))
        if len(results) >= limit:
            break
    return results


def _evidence_has_conflict(candidates: list[_EvidenceCandidate], favorite_label: str) -> bool:
    favorite = _favorite_tokens(favorite_label)
    if not favorite:
        return False
    favorite_support = False
    opposing_support = False
    for candidate in candidates[:5]:
        if candidate.signal_hits == 0:
            continue
        if favorite & candidate.tokens:
            favorite_support = True
        elif candidate.team_hits >= 1:
            opposing_support = True
    return favorite_support and opposing_support


def _context_threshold_reference(report: schema.Report, threshold: float) -> Optional[float]:
    values: list[float] = []
    for item in list(report.polymarket) + list(report.kalshi):
        values.extend(_threshold_numbers(f"{getattr(item, 'title', '')} {getattr(item, 'question', '')}"))
    for item in list(report.x[:8]) + list(report.reddit[:5]) + list(report.web[:5]):
        values.extend(_threshold_numbers(f"{getattr(item, 'title', '')} {getattr(item, 'content', '')} {getattr(item, 'summary', '')}"))
    plausible = [value for value in values if 1_000 <= value < threshold * 0.98]
    return max(plausible) if plausible else None


def _format_threshold_value(value: float) -> str:
    if value >= 1_000_000:
        formatted = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"${formatted}M"
    if value >= 1_000:
        formatted = f"{value / 1_000:.0f}" if value % 1_000 == 0 else f"{value / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"${formatted}k"
    return f"${value:.0f}"


def _threshold_window_phrase(window: Optional[str]) -> str:
    if window == "this_week":
        return "this week"
    if window == "this_month":
        return "this month"
    if window == "this_year":
        return "this year"
    return "on the current horizon"


def _crypto_context_phrase(tokens: set[str]) -> str:
    if (tokens & {"etf", "etfs"}) and (tokens & {"flow", "flows"}) and (tokens & {"liquidity", "exchange", "exchanges"}):
        return "ETF flows and exchange-liquidity context"
    if (tokens & {"etf", "etfs"}) and (tokens & {"flow", "flows"}):
        return "ETF flow context"
    if tokens & {"liquidity", "exchange", "exchanges", "repricing"}:
        return "liquidity and repricing context"
    if "spot" in tokens and tokens & {"price", "prices", "support", "resistance", "volume", "momentum", "breakout"}:
        return "spot-price market structure"
    return "market-structure context"


def _crypto_threshold_why_line(
    report: schema.Report,
    title: str,
    evidence_candidates: list[_EvidenceCandidate],
) -> str:
    topic_spec = _threshold_spec(title)
    if topic_spec.entity not in _CRYPTO_ENTITY_ALIASES or topic_spec.threshold is None:
        return ""
    target_text = _format_threshold_value(topic_spec.threshold)
    entity_text = (topic_spec.entity or "Crypto").capitalize()
    window_text = _threshold_window_phrase(topic_spec.window)

    preferred_non_social = next(
        (
            candidate
            for candidate in evidence_candidates
            if candidate.source not in _SOCIAL_SOURCES and _allow_crypto_evidence(title, candidate.text)
        ),
        None,
    )
    if preferred_non_social:
        return preferred_non_social.text

    preferred_social = next(
        (
            candidate
            for candidate in evidence_candidates
            if candidate.source in _SOCIAL_SOURCES and _social_crypto_context_ok(candidate.tokens, _topic_tokens(title))
        ),
        None,
    )
    if not preferred_social:
        preferred_social = _crypto_threshold_context_candidate(report, title)
    if not preferred_social:
        return ""

    candidate_values = [value for value in _threshold_numbers(preferred_social.text) if 1_000 <= value < topic_spec.threshold]
    reference = max(candidate_values) if candidate_values else _context_threshold_reference(report, topic_spec.threshold)
    context_phrase = _crypto_context_phrase(preferred_social.tokens)
    if reference:
        reference_text = _format_threshold_value(reference)
        return (
            f"{entity_text} is still trading closer to {reference_text} than {target_text}; "
            f"the clean evidence is mostly {context_phrase}, not a direct move through {target_text} {window_text}."
        )
    return (
        f"{entity_text} is still below the {target_text} target; "
        f"the clean evidence is mostly {context_phrase}, not a direct break through {target_text} {window_text}."
    )


def _crypto_threshold_context_candidate(report: schema.Report, title: str) -> Optional[_EvidenceCandidate]:
    title_tokens = _topic_tokens(title)
    topic_spec = _threshold_spec(title)
    topic_entities = title_tokens & _CRYPTO_ENTITY_TOKENS
    best: Optional[_EvidenceCandidate] = None
    primary_market_terms = {"flow", "flows", "liquidity", "exchange", "exchanges", "repricing"}
    secondary_market_terms = {"spot", "price", "prices", "volume", "momentum", "support", "resistance", "breakout", "etf", "etfs"}

    for source_name, items in (("x", report.x[:12]), ("reddit", report.reddit[:10]), ("web", report.web[:8])):
        for item in items:
            text = (
                getattr(item, "text", "")
                or getattr(item, "title", "")
                or getattr(item, "snippet", "")
                or ""
            )
            if not text:
                continue
            context = getattr(item, "author_handle", "") or getattr(item, "subreddit", "") or getattr(item, "source_domain", "")
            tokens = _tokenize(f"{text} {context}")
            if topic_entities and not (topic_entities & tokens):
                continue
            if _social_noise_tokens(tokens):
                continue
            if not ((tokens & primary_market_terms) or (tokens & secondary_market_terms)):
                continue
            score = float(getattr(item, "score", 0) or 0)
            if tokens & primary_market_terms:
                score += 12
            if topic_spec.threshold is not None:
                numbers = [value for value in _threshold_numbers(text) if value >= 1_000]
                if any(abs(value - topic_spec.threshold) <= max(500.0, topic_spec.threshold * 0.05) for value in numbers):
                    score += 8
                elif any(value < topic_spec.threshold for value in numbers):
                    score += 4
            candidate = _EvidenceCandidate(
                score=score,
                text=text.strip(),
                tokens=tokens,
                source=source_name,
                team_hits=0,
                signal_hits=len(tokens & (_CRYPTO_STRONG_SIGNAL_TERMS | primary_market_terms | secondary_market_terms)),
            )
            if best is None or candidate.score > best.score:
                best = candidate
    return best


def _model_implied_range(report: schema.Report) -> tuple[float, float]:
    topic_spec = _threshold_spec(report.topic)
    if topic_spec.entity in _CRYPTO_ENTITY_ALIASES and topic_spec.direction == "above" and topic_spec.threshold:
        reference = _context_threshold_reference(report, topic_spec.threshold)
        ratio = (topic_spec.threshold / reference) if reference else None
        if topic_spec.window == "this_week":
            if ratio and ratio >= 1.30:
                return 0.03, 0.12
            if ratio and ratio >= 1.20:
                return 0.05, 0.18
            if ratio and ratio >= 1.10:
                return 0.12, 0.32
            return 0.08, 0.25
        if topic_spec.window == "this_month":
            if ratio and ratio >= 1.30:
                return 0.08, 0.22
            if ratio and ratio >= 1.20:
                return 0.12, 0.30
    if topic_spec.entity in _CRYPTO_ENTITY_ALIASES and topic_spec.direction == "below" and topic_spec.threshold:
        reference = _context_threshold_reference(report, topic_spec.threshold * 2)
        if reference and reference / topic_spec.threshold >= 1.20 and topic_spec.window == "this_week":
            return 0.05, 0.18
    evidence_count = len(report.x[:5]) + len(report.reddit[:5]) + len(report.web[:5])
    if evidence_count >= 5:
        return 0.48, 0.58
    if evidence_count >= 2:
        return 0.44, 0.58
    return 0.40, 0.60


def _weather_probability(report: schema.Report) -> tuple[Optional[schema.WeatherItem], Optional[float]]:
    if not report.weather:
        return None, None
    item = report.weather[0]
    if item.probability is None:
        return item, None
    return item, max(0.0, min(1.0, item.probability))


def _confidence_label(spread: Optional[float], quality: float, evidence_count: int, has_market: bool) -> str:
    if not has_market:
        return "low"
    if spread is not None and spread >= 0.12:
        return "moderate-low"
    if quality >= 0.65 and evidence_count >= 3:
        return "moderate"
    if quality >= 0.45:
        return "moderate-low"
    return "low"


def _uncertainty_text(
    confidence: str,
    spread: Optional[float],
    has_both_markets: bool,
    has_market: bool,
    evidence_count: int,
    evidence_conflict: bool = False,
) -> str:
    if not has_market:
        return "No clean market exists, so this is model-implied and should be treated cautiously."
    parts = []
    if has_both_markets and spread is not None:
        if spread >= 0.12:
            parts.append(f"Polymarket and Kalshi disagree by about {spread * 100:.0f} points.")
        elif spread >= 0.05:
            parts.append(f"Polymarket and Kalshi are directionally aligned but still {spread * 100:.0f} points apart.")
        else:
            parts.append("Polymarket and Kalshi are broadly aligned.")
    if evidence_count < 2:
        parts.append("Supporting non-market evidence is thin.")
    elif evidence_conflict:
        parts.append("Recent non-market evidence is mixed, so the market line still carries most of the weight.")
    if confidence == "moderate":
        parts.append("Confidence is moderate for a live market-backed forecast.")
    elif confidence == "moderate-low":
        parts.append("Confidence is moderate-low because the line is still sensitive to fresh information.")
    else:
        parts.append("Confidence is low.")
    return " ".join(parts)


def _generic_catalysts(report: schema.Report, favorite_label: str) -> tuple[list[str], list[str]]:
    topic = report.topic.lower()
    if any(term in topic for term in ("rain", "snow", "storm", "weather", "temperature", "wind")):
        return (
            ["More severe radar/model runs", "New watches or warnings"],
            ["A weaker storm track", "Drying trend in updated weather models"],
        )
    if any(term in topic for term in ("bitcoin", "btc", "ethereum", "eth", "crypto", "coin", "token")):
        return (
            ["Stronger spot price momentum", "ETF flows or liquidity improving alongside market repricing"],
            ["Spot price rejection near resistance", "Risk-off macro move or sharp prediction-market repricing"],
        )
    if any(term in topic for term in ("election", "poll", "approval", "rate cut", "inflation", "cpi", "fed", "recession", "gdp", "jobs")):
        return (
            ["Fresh polling or data releases that favor the market direction", "Official statements that reinforce the current line"],
            ["Contradictory data or polling", "Sharp repricing in related macro or prediction markets"],
        )
    label = favorite_label or "the current favorite"
    return (
        [f"Positive lineup/injury news for {label}", "Supportive late market movement"],
        [f"Negative lineup/injury news for {label}", "Any sharp move against the current favorite near the event"],
    )


def _generic_fallback_why_line(report: schema.Report) -> str:
    topic = report.topic.lower()
    if _is_weather_query(topic):
        if report.weather_error:
            return f"Model-implied because no clean market or official weather anchor was available: {report.weather_error}."
        return "Model-implied because no clean market exists and no high-signal weather evidence surfaced in the last 24 hours."
    if _is_macro_query(topic):
        return "Mostly market-driven right now; no high-signal macro or policy evidence surfaced in the last 24 hours."
    return "Mostly market-driven right now; supporting evidence is thin."


def _degraded_forecast_warning(report: schema.Report) -> str:
    topic = report.topic
    if _is_esports_match_query(topic):
        return (
            "DEGRADED RUN WARNING: no date-compatible direct eSports market "
            "cleared anchoring, so this is a lower-confidence model-implied forecast."
        )
    if _is_sports_query(topic):
        return (
            "DEGRADED RUN WARNING: no date-compatible Polymarket/Kalshi game market "
            "cleared anchoring, so this is a lower-confidence model-implied forecast."
        )
    topic_spec = _threshold_spec(topic)
    if topic_spec.threshold is not None:
        return (
            "DEGRADED RUN WARNING: no threshold-compatible Polymarket/Kalshi market "
            "cleared anchoring, so this is a lower-confidence model-implied forecast."
        )
    if _is_weather_query(topic):
        return (
            "DEGRADED RUN WARNING: no clean market or official weather anchor cleared, "
            "so this is a lower-confidence model-implied forecast."
        )
    if _is_macro_query(topic):
        return (
            "DEGRADED RUN WARNING: no clean Fed/macro market cleared anchoring, so this "
            "is a lower-confidence model-implied forecast."
        )
    return (
        "DEGRADED RUN WARNING: no clean Polymarket/Kalshi market cleared anchoring, "
        "so this is a lower-confidence model-implied forecast."
    )


def _sports_catalysts(candidates: list[_EvidenceCandidate], favorite_label: str) -> tuple[list[str], list[str]]:
    favorite = favorite_label or "the favorite"
    if favorite.lower() in {"yes", "no"}:
        favorite = "the forecast side"
    all_tokens = set()
    for candidate in candidates[:5]:
        all_tokens |= candidate.tokens

    up = []
    down = []

    if {"questionable", "doubtful", "out", "inactive"} & all_tokens:
        up.append(f"Positive availability news for {favorite}")
        down.append(f"A downgrade or scratch for {favorite}")
    if {"rest", "resting", "back-to-back", "b2b", "minutes", "restriction", "restricted"} & all_tokens:
        up.append("A softer rest/minutes spot than expected")
        down.append("A tougher rest spot or minutes restriction")
    if {"lineup", "lineups", "starter", "starters", "starting"} & all_tokens:
        up.append(f"A stronger-than-expected starting lineup for {favorite}")
        down.append("A surprise lineup downgrade")
    if {"playoff", "playoffs", "seed", "seeding", "elimination", "clinch", "clinched", "tank", "tanking"} & all_tokens:
        up.append("Clearer playoff or motivation edge")
        down.append("Motivation or seeding incentives breaking the other way")
    if not up:
        up.append(f"Positive lineup/injury news for {favorite}")
    if not down:
        down.append(f"Negative lineup/injury news for {favorite}")
    if len(up) < 2:
        up.append("Supportive late market movement")
    if len(down) < 2:
        down.append("Any sharp move against the current favorite near tipoff")
    return up[:2], down[:2]


def _esports_catalysts(candidates: list[_EvidenceCandidate], favorite_label: str) -> tuple[list[str], list[str]]:
    favorite = favorite_label or "the forecast side"
    all_tokens = set()
    for candidate in candidates[:5]:
        all_tokens |= candidate.tokens

    up = []
    down = []

    if {"roster", "standin", "stand-in", "sub", "substitute", "bench", "benched", "coach"} & all_tokens:
        up.append(f"Supportive roster or stand-in news for {favorite}")
        down.append(f"Negative roster or stand-in news for {favorite}")
    if {"patch", "update", "map", "pool", "veto"} & all_tokens:
        up.append("A favorable patch, map-pool, or veto setup")
        down.append("A patch, map-pool, or veto shift moving against the current side")
    if {"qualifier", "qualifiers", "playoff", "playoffs", "bracket", "elimination", "seed", "seeding", "lan"} & all_tokens:
        up.append("Bracket or tournament context strengthening the current side")
        down.append("Bracket or tournament context breaking the other way")
    if len(up) < 2:
        up.append("Supportive late market movement")
    if len(down) < 2:
        down.append("Any sharp move against the current side near match time")
    return up[:2], down[:2]


def _build_forecast_item(
    title: str,
    polymarket_item: Optional[schema.PolymarketItem],
    kalshi_item: Optional[schema.KalshiItem],
    report: schema.Report,
) -> schema.ForecastItem:
    evidence_candidates = _collect_evidence_candidates(report, title)
    evidence = []
    for candidate in evidence_candidates:
        short = candidate.text.replace("\n", " ")[:180].strip()
        if short and short not in evidence:
            evidence.append(short + ("..." if len(candidate.text) > 180 else ""))
        if len(evidence) >= 2:
            break
    evidence_count = len(evidence)
    macro_query = _is_macro_query(title) or _is_macro_query(report.topic)
    crypto_threshold_query = _is_crypto_query(title) and _threshold_spec(title).threshold is not None
    esports_query = _is_esports_query(title) or _is_esports_query(report.topic)

    poly_label, poly_probability = (None, None)
    if polymarket_item:
        poly_label, poly_probability = _polymarket_probability_for_topic(polymarket_item, report.topic)
    kalshi_probability = kalshi_item.current_probability if kalshi_item else None
    weather_item, weather_probability = _weather_probability(report)

    poly_quality = market_quality(
        polymarket_item.engagement if polymarket_item else None,
        polymarket_item.price_movement_pct if polymarket_item else None,
    ) if polymarket_item else 0.0
    kalshi_quality = market_quality(
        kalshi_item.engagement if kalshi_item else None,
        kalshi_item.price_movement_pct if kalshi_item else None,
    ) if kalshi_item else 0.0

    forecast = schema.ForecastItem(title=title)
    forecast.favorite_label = poly_label or "Yes"
    if macro_query:
        preferred_macro = next((candidate for candidate in evidence_candidates if _macro_quality_lead_ok(candidate)), None)
        if preferred_macro:
            forecast.why_line = preferred_macro.text
        else:
            strong_social = next(
                (
                    candidate for candidate in evidence_candidates
                    if candidate.source in _SOCIAL_SOURCES and _macro_social_lead_ok(candidate.tokens)
                ),
                None,
            )
            forecast.why_line = strong_social.text if strong_social else ""
    elif esports_query:
        forecast.why_line = evidence[0] if evidence else ""
    elif crypto_threshold_query:
        forecast.why_line = _crypto_threshold_why_line(report, title, evidence_candidates)
    else:
        forecast.why_line = evidence[0] if evidence else ""
    forecast.polymarket_market_id = polymarket_item.id if polymarket_item else None
    forecast.kalshi_market_id = kalshi_item.id if kalshi_item else None
    forecast.polymarket_probability = poly_probability
    forecast.kalshi_probability = kalshi_probability

    if poly_probability is not None and kalshi_probability is not None:
        poly_weight = max(0.15, poly_quality or 0.0)
        kalshi_weight = max(0.15, kalshi_quality or 0.0)
        blended = ((poly_probability * poly_weight) + (kalshi_probability * kalshi_weight)) / (poly_weight + kalshi_weight)
        spread = abs(poly_probability - kalshi_probability)
        range_half = 0.04 + min(0.12, spread / 2)
        forecast.forecast_probability = blended
        forecast.forecast_range_low = max(0.01, blended - range_half)
        forecast.forecast_range_high = min(0.99, blended + range_half)
        forecast.anchor_source = "blended"
        forecast.market_spread = spread
        forecast.market_view = (
            f"Polymarket {poly_probability * 100:.0f}% | Kalshi {kalshi_probability * 100:.0f}% "
            f"(spread {spread * 100:.0f} pts; {'Polymarket' if poly_weight >= kalshi_weight else 'Kalshi'} carries more weight)"
        )
        quality = max(poly_quality, kalshi_quality)
        forecast.confidence_level = _confidence_label(spread, quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            spread,
            True,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    elif poly_probability is not None:
        range_half = 0.04 if poly_quality >= 0.5 else 0.07
        forecast.forecast_probability = poly_probability
        forecast.forecast_range_low = max(0.01, poly_probability - range_half)
        forecast.forecast_range_high = min(0.99, poly_probability + range_half)
        forecast.anchor_source = "polymarket"
        movement = f" ({polymarket_item.price_movement})" if polymarket_item and polymarket_item.price_movement else ""
        forecast.market_view = f"Polymarket {poly_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, poly_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            None,
            False,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    elif kalshi_probability is not None:
        range_half = 0.05 if kalshi_quality >= 0.5 else 0.08
        forecast.forecast_probability = kalshi_probability
        forecast.forecast_range_low = max(0.01, kalshi_probability - range_half)
        forecast.forecast_range_high = min(0.99, kalshi_probability + range_half)
        forecast.anchor_source = "kalshi"
        movement = f" ({kalshi_item.price_movement})" if kalshi_item and kalshi_item.price_movement else ""
        forecast.market_view = f"Kalshi {kalshi_probability * 100:.0f}%{movement}"
        forecast.confidence_level = _confidence_label(None, kalshi_quality, evidence_count, has_market=True)
        forecast.uncertainty = _uncertainty_text(
            forecast.confidence_level,
            None,
            False,
            True,
            evidence_count,
            evidence_conflict=_evidence_has_conflict(evidence_candidates, forecast.favorite_label),
        )
    elif weather_probability is not None and (_is_weather_query(title) or _is_weather_query(report.topic)):
        range_half = 0.05
        forecast.forecast_probability = weather_probability
        forecast.forecast_range_low = max(0.01, weather_probability - range_half)
        forecast.forecast_range_high = min(0.99, weather_probability + range_half)
        forecast.anchor_source = "weather_api"
        forecast.favorite_label = "Yes"
        forecast.model_implied = False
        probability_pct = weather_item.probability_pct if weather_item else round(weather_probability * 100)
        location = weather_item.location if weather_item else "the requested location"
        forecast_date = weather_item.forecast_date if weather_item else report.range_to
        forecast.market_view = f"NWS {probability_pct}% peak precipitation probability for {location} on {forecast_date}"
        details = []
        if weather_item and weather_item.short_forecast:
            details.append(weather_item.short_forecast)
        if weather_item and weather_item.temperature is not None:
            details.append(f"{weather_item.temperature} deg {weather_item.temperature_unit}")
        if weather_item and weather_item.wind:
            details.append(f"wind {weather_item.wind}")
        forecast.why_line = "Official NWS hourly forecast: " + "; ".join(details) if details else "Official NWS hourly forecast provides the current weather anchor."
        forecast.confidence_level = "moderate-low"
        forecast.uncertainty = "Official NWS forecast is the anchor, but local precipitation timing can still move as newer model runs update."
    else:
        low, high = _model_implied_range(report)
        forecast.model_implied = True
        forecast.forecast_probability = (low + high) / 2
        forecast.forecast_range_low = low
        forecast.forecast_range_high = high
        forecast.anchor_source = "model_implied"
        forecast.market_view = "No clean Polymarket or Kalshi market found."
        forecast.degraded_warning = _degraded_forecast_warning(report)
        forecast.confidence_level = _confidence_label(None, 0.0, evidence_count, has_market=False)
        forecast.uncertainty = _uncertainty_text(forecast.confidence_level, None, False, False, evidence_count)
        _rerank_degraded_source_items(report, title)

    if esports_query:
        forecast.upside_catalysts, forecast.downside_catalysts = _esports_catalysts(evidence_candidates, forecast.favorite_label)
        if not forecast.why_line:
            if forecast.anchor_source in {"polymarket", "kalshi", "blended"}:
                forecast.why_line = "Mostly market-driven right now; no clean roster, patch, veto, or tournament-context driver surfaced in the last 24 hours."
            else:
                forecast.why_line = "No clean market exists and no high-signal roster, patch, veto, or tournament-context driver surfaced in the last 24 hours."
    elif _is_sports_query(title) or _is_sports_query(report.topic):
        forecast.upside_catalysts, forecast.downside_catalysts = _sports_catalysts(evidence_candidates, forecast.favorite_label)
        if not forecast.why_line:
            if forecast.anchor_source in {"polymarket", "kalshi", "blended"}:
                forecast.why_line = "Mostly market-driven right now; no clean injury, lineup, rest, or market-moving team signal surfaced in the last 24 hours."
            else:
                forecast.why_line = "No clean market exists and no high-signal team-specific driver surfaced in the last 24 hours."
    else:
        forecast.upside_catalysts, forecast.downside_catalysts = _generic_catalysts(report, forecast.favorite_label)
        if not forecast.why_line:
            forecast.why_line = _generic_fallback_why_line(report)
    return forecast


def synthesize_forecasts(report: schema.Report) -> list[schema.ForecastItem]:
    """Create market-anchored forecast objects for prediction queries."""
    if qt.detect_query_type(report.topic) != "prediction":
        return []

    forecasts: list[schema.ForecastItem] = []
    topic_lower = report.topic.lower()
    is_nba_slate = "nba" in topic_lower and any(term in topic_lower for term in ("games", "matchups", "slate"))
    is_esports_slate = _is_esports_match_query(report.topic) and any(term in topic_lower for term in ("matches", "games")) and not _is_esports_player_prop_query(report.topic)
    sports_target_date = _sports_target_date(report) if (_is_sports_query(report.topic) or _is_esports_query(report.topic)) else None

    if is_nba_slate and (report.polymarket or report.kalshi):
        slate_rows: dict[str, dict[str, object]] = {}
        slate_order: dict[str, int] = {}

        for poly_item in report.polymarket:
            if (
                not _is_nba_market_item(poly_item)
                or not _is_direct_game_market(poly_item)
                or not _sports_market_date_compatible(poly_item, sports_target_date)
            ):
                continue
            signature = _item_matchup_signature(poly_item)
            if not signature:
                continue
            row = slate_rows.setdefault(signature, {"polymarket": None, "kalshi": None, "title": poly_item.title or poly_item.question})
            if row["polymarket"] is None or poly_item.score > row["polymarket"].score:
                row["polymarket"] = poly_item
                row["title"] = poly_item.title or poly_item.question
            slate_order[signature] = max(slate_order.get(signature, 0), poly_item.score)

        for kalshi_item in report.kalshi:
            if (
                not _is_nba_market_item(kalshi_item)
                or not _is_direct_game_market(kalshi_item)
                or not _sports_market_date_compatible(kalshi_item, sports_target_date)
            ):
                continue
            signature = _item_matchup_signature(kalshi_item)
            if not signature:
                continue
            row = slate_rows.setdefault(signature, {"polymarket": None, "kalshi": None, "title": kalshi_item.title or kalshi_item.question})
            if row["kalshi"] is None or kalshi_item.score > row["kalshi"].score:
                row["kalshi"] = kalshi_item
                if not row["polymarket"]:
                    row["title"] = kalshi_item.title or kalshi_item.question
            slate_order[signature] = max(slate_order.get(signature, 0), kalshi_item.score)

        for signature in sorted(slate_rows, key=lambda key: slate_order.get(key, 0), reverse=True):
            row = slate_rows[signature]
            poly_item = row["polymarket"]
            kalshi_item = row["kalshi"]
            title = str(row["title"] or report.topic)
            forecasts.append(_build_forecast_item(title, poly_item, kalshi_item, report))
        return forecasts

    if is_esports_slate and report.polymarket:
        slate_rows: dict[str, schema.PolymarketItem] = {}
        slate_order: dict[str, int] = {}
        topic_subdomain = eq.esports_subdomain_of(report.topic)
        for poly_item in report.polymarket:
            if (
                not _is_esports_market_item(poly_item)
                or not _is_direct_game_market(poly_item)
                or not _sports_market_date_compatible(poly_item, sports_target_date)
            ):
                continue
            if topic_subdomain and eq.esports_subdomain_of(f"{poly_item.title} {poly_item.question} {poly_item.url}") != topic_subdomain:
                continue
            signature = _item_matchup_signature(poly_item)
            if not signature:
                continue
            if signature not in slate_rows or poly_item.score > slate_rows[signature].score:
                slate_rows[signature] = poly_item
            slate_order[signature] = max(slate_order.get(signature, 0), poly_item.score)
        for signature in sorted(slate_rows, key=lambda key: slate_order.get(key, 0), reverse=True):
            poly_item = slate_rows[signature]
            forecasts.append(_build_forecast_item(poly_item.title or poly_item.question or report.topic, poly_item, None, report))
        if forecasts:
            return forecasts

    allow_esports_prop = _is_esports_player_prop_query(report.topic)
    top_poly = _best_polymarket(report.topic, report.polymarket, sports_target_date, allow_esports_prop=allow_esports_prop)
    top_kalshi = _best_kalshi(report.topic, report.kalshi, sports_target_date, allow_esports_prop=allow_esports_prop)
    if top_poly and top_kalshi and _item_matchup_signature(top_poly):
        matched_kalshi = _matching_kalshi_for_polymarket(top_poly, report.kalshi, sports_target_date, allow_esports_prop=allow_esports_prop)
        if matched_kalshi:
            top_kalshi = matched_kalshi

    title = top_poly.title if top_poly else top_kalshi.title if top_kalshi else report.topic
    forecasts.append(_build_forecast_item(title, top_poly, top_kalshi, report))
    return forecasts
