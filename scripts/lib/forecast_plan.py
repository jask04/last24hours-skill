"""Deterministic forecast/search planning inspired by last30days v3.

This is intentionally small: it expands search topics and records source
weights without replacing the market-first retrieval pipeline.
"""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional

from . import evidence_quality as eq, market_watchlist, query_type as qt


@dataclass
class PlannedQuery:
    label: str
    search_query: str
    sources: List[str]
    weight: float = 1.0


@dataclass
class ForecastPlan:
    topic: str
    query_type: qt.QueryType
    depth: str
    subqueries: List[PlannedQuery] = field(default_factory=list)
    source_weights: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    entity_resolution_used: bool = False

    @property
    def search_topics(self) -> List[str]:
        topics = []
        seen = set()
        for subquery in self.subqueries:
            key = subquery.search_query.lower()
            if key and key not in seen:
                topics.append(subquery.search_query)
                seen.add(key)
        return topics

    def to_source_info(self) -> Dict[str, object]:
        return {
            "planned_query_count": len(self.subqueries),
            "planned_queries": [q.search_query for q in self.subqueries],
            "planner_notes": "; ".join(self.notes),
        }


_GENERIC_FORECAST_WORDS = re.compile(
    r"\b("
    r"will|would|could|should|chance|odds|probability|forecast|prediction|"
    r"market|markets|watch|recommend|best|today|tomorrow|tonight|this week|"
    r"by|before|after|around|right now"
    r")\b",
    re.I,
)

_MACRO_TERMS = {
    "fed", "fomc", "powell", "rates", "rate", "cut", "cuts", "hike",
    "inflation", "cpi", "jobs", "payrolls", "gdp", "recession",
    "unemployment", "treasury", "yield",
}


def _source_weights(query_type: qt.QueryType) -> Dict[str, float]:
    if query_type == "market_watchlist":
        return {
            "kalshi": 1.00,
            "polymarket": 0.98,
            "web": 0.62,
            "x": 0.52,
            "reddit": 0.44,
            "hn": 0.32,
        }
    if query_type == "prediction":
        return {
            "kalshi": 1.00,
            "polymarket": 0.98,
            "weather": 0.92,
            "x": 0.50,
            "reddit": 0.42,
            "web": 0.46,
            "hn": 0.30,
            "bluesky": 0.22,
            "truthsocial": 0.18,
        }
    return {"web": 0.55, "reddit": 0.50, "x": 0.48, "hn": 0.36}


def _clean_topic(topic: str) -> str:
    cleaned = _GENERIC_FORECAST_WORDS.sub(" ", topic or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:?")
    return cleaned or (topic or "").strip()


def _macro_queries(topic: str) -> List[str]:
    tokens = set(re.sub(r"[^\w\s]", " ", topic.lower()).split())
    queries = [topic]
    if tokens & {"fed", "fomc", "powell", "rates", "rate", "cut", "cuts", "hike"}:
        queries.append("Fed rate cuts")
    if tokens & {"inflation", "cpi"}:
        queries.append("CPI inflation")
    if tokens & {"jobs", "payrolls", "unemployment"}:
        queries.append("jobs report unemployment")
    if "recession" in tokens:
        queries.append("US recession indicators")
    return queries


def _deterministic_queries(topic: str, query_type: qt.QueryType, search_topics: Optional[List[str]]) -> List[str]:
    if search_topics:
        return search_topics
    if query_type == "market_watchlist":
        return market_watchlist.search_topics(topic)
    if eq.is_weather_query(topic):
        cleaned = _clean_topic(topic)
        return [topic, f"{cleaned} forecast"]
    if eq.is_macro_query(topic) or set(re.sub(r"[^\w\s]", " ", topic.lower()).split()) & _MACRO_TERMS:
        return _macro_queries(topic)
    cleaned = _clean_topic(topic)
    if cleaned and cleaned.lower() != topic.lower():
        return [topic, cleaned]
    return [topic]


def build_plan(
    topic: str,
    query_type: qt.QueryType,
    depth: str,
    search_topics: Optional[List[str]] = None,
    web_backend: Optional[str] = None,
) -> ForecastPlan:
    """Build a bounded deterministic plan for retrieval and evidence fusion."""
    max_queries = 3 if depth == "quick" else 5
    topics = []
    seen = set()
    for candidate in _deterministic_queries(topic, query_type, search_topics):
        normalized = re.sub(r"\s+", " ", (candidate or "").strip())
        key = normalized.lower()
        if normalized and key not in seen:
            topics.append(normalized)
            seen.add(key)
        if len(topics) >= max_queries:
            break

    weights = _source_weights(query_type)
    market_first_sources = ["kalshi", "polymarket", "x", "reddit", "web", "hn"]
    if query_type != "prediction":
        market_first_sources = ["web", "reddit", "x", "hn"]
    if query_type == "market_watchlist":
        market_first_sources = ["kalshi", "polymarket", "web", "x", "reddit", "hn"]

    subqueries = [
        PlannedQuery(
            label=f"q{idx}",
            search_query=query,
            sources=market_first_sources,
            weight=max(0.20, 1.0 - ((idx - 1) * 0.15)),
        )
        for idx, query in enumerate(topics or [topic], start=1)
    ]

    notes = ["deterministic-plan"]
    entity_resolution_used = False
    if depth == "quick":
        notes.append("quick-no-entity-resolution")
    elif web_backend:
        # V1 records capability and keeps the run deterministic. Future rounds can
        # use this hook to make a bounded native-web resolve call.
        notes.append(f"entity-resolution-available:{web_backend}")
    else:
        notes.append("entity-resolution-skipped:no-native-web")

    return ForecastPlan(
        topic=topic,
        query_type=query_type,
        depth=depth,
        subqueries=subqueries,
        source_weights=weights,
        notes=notes,
        entity_resolution_used=entity_resolution_used,
    )
