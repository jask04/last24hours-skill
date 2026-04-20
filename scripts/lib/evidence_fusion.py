"""Cross-source evidence fusion for forecast explanations and watchlists."""

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional, Tuple

from . import evidence_quality as eq, query_type as qt, schema


@dataclass
class FusedEvidence:
    text: str
    source: str
    source_item_id: str
    author_key: str
    cluster_key: str
    score: float


@dataclass
class FusionResult:
    drivers: List[FusedEvidence]
    candidate_count: int
    cluster_count: int

    def stats(self) -> dict:
        return {
            "candidate_count": self.candidate_count,
            "driver_count": len(self.drivers),
            "cluster_count": self.cluster_count,
        }


_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "will", "would",
    "could", "should", "today", "tomorrow", "tonight", "game", "games",
    "market", "markets", "forecast", "probability", "chance",
}

_SOURCE_BASE = {
    "web": 0.68,
    "x": 0.56,
    "reddit": 0.50,
    "hackernews": 0.42,
    "bluesky": 0.35,
    "truthsocial": 0.30,
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.sub(r"[^\w\s-]", " ", (text or "").lower()).split()
        if len(token) > 2 and token not in _STOP
    }


def _topic_tokens(topic: str) -> set[str]:
    return _tokens(topic)


def _trim(text: str, limit: int = 190) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _source_rows(report: schema.Report) -> Iterable[Tuple[str, object, str, str, str]]:
    for item in report.x[:24]:
        yield "x", item, item.text, item.author_handle, item.id
    for item in report.reddit[:18]:
        comments = " ".join(item.comment_insights[:2])
        yield "reddit", item, f"{item.title} {comments}", item.subreddit, item.id
    for item in report.web[:18]:
        yield "web", item, f"{item.title} {item.snippet}", item.source_domain, item.id
    for item in report.hackernews[:10]:
        yield "hackernews", item, item.title, "news.ycombinator.com", item.id
    for item in report.bluesky[:8]:
        yield "bluesky", item, item.text, item.author_handle, item.id
    for item in report.truthsocial[:8]:
        yield "truthsocial", item, item.text, item.author_handle, item.id


def _cluster_key(tokens: set[str], topic_tokens: set[str]) -> str:
    overlap = sorted((tokens & topic_tokens) or tokens)
    return " ".join(overlap[:4])


def _is_signal(topic: str, text: str, context: str, query_type: qt.QueryType) -> bool:
    tokens = _tokens(f"{text} {context}")
    topic_tokens = _topic_tokens(topic)
    if query_type == "prediction" and (eq.is_weather_query(topic) or eq.WEATHER_QUERY_TERMS & topic_tokens):
        return eq.is_weather_signal(text, topic_tokens, context, require_location=False)
    if query_type == "prediction" and eq.is_macro_query(topic):
        return eq.is_macro_signal(text, topic_tokens, context)
    if query_type == "prediction" and (eq.SPORTS_TEAM_TOKENS & (tokens | topic_tokens) or "nba" in topic_tokens):
        category = eq.classify_sports_evidence(
            text,
            context,
            exact_match=bool(tokens & topic_tokens),
            exact_date=False,
            allow_market_context=False,
        )
        return category == "high_signal"
    return bool(tokens & (eq.DRIVER_TERMS | eq.MACRO_SIGNAL_TERMS | eq.WEATHER_SIGNAL_TERMS))


def _score(topic: str, text: str, context: str, source: str, base_score: int, query_type: qt.QueryType) -> Optional[float]:
    tokens = _tokens(f"{text} {context}")
    topic_tokens = _topic_tokens(topic)
    overlap = len(tokens & topic_tokens)
    if overlap == 0 and query_type in {"prediction", "market_watchlist"}:
        if not (tokens & (eq.DRIVER_TERMS | eq.MACRO_SIGNAL_TERMS | eq.WEATHER_SIGNAL_TERMS)):
            return None
    if not _is_signal(topic, text, context, query_type):
        return None

    source_base = _SOURCE_BASE.get(source, 0.35)
    score = source_base + min(0.28, (base_score or 0) / 350.0) + min(0.22, overlap * 0.04)
    signal_hits = len(tokens & (eq.DRIVER_TERMS | eq.MACRO_SIGNAL_TERMS | eq.WEATHER_SIGNAL_TERMS))
    score += min(0.25, signal_hits * 0.04)
    if query_type == "prediction" and (eq.SPORTS_TEAM_TOKENS & (tokens | topic_tokens) or "nba" in topic_tokens):
        sports_category = eq.classify_sports_evidence(
            text,
            context,
            exact_match=bool(tokens & topic_tokens),
            exact_date=False,
            allow_market_context=False,
        )
        if sports_category == "high_signal":
            score += 0.12
        if sports_category in {"low_signal", "generic_preview", "reject"}:
            score -= 0.30
    return max(0.0, score)


def fuse_evidence(
    report: schema.Report,
    topic: Optional[str] = None,
    query_type: Optional[qt.QueryType] = None,
    limit: int = 4,
) -> FusionResult:
    """Return high-signal non-market evidence with author caps and clustering."""
    topic = topic or report.topic
    query_type = query_type or qt.detect_query_type(report.topic)
    topic_tokens = _topic_tokens(topic)
    candidates: List[FusedEvidence] = []

    for source, item, text, context, item_id in _source_rows(report):
        score = _score(topic, text, context, source, getattr(item, "score", 0), query_type)
        if score is None:
            continue
        tokens = _tokens(f"{text} {context}")
        key = _cluster_key(tokens, topic_tokens)
        if not key:
            continue
        candidates.append(
            FusedEvidence(
                text=_trim(text),
                source=source,
                source_item_id=item_id,
                author_key=f"{source}:{(context or '').lower()}",
                cluster_key=key,
                score=score,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    author_counts = {}
    clusters = {}
    selected: List[FusedEvidence] = []
    for candidate in candidates:
        if author_counts.get(candidate.author_key, 0) >= 2:
            continue
        existing = clusters.get(candidate.cluster_key)
        if existing and existing.score >= candidate.score:
            continue
        if existing and existing in selected:
            selected.remove(existing)
        clusters[candidate.cluster_key] = candidate
        author_counts[candidate.author_key] = author_counts.get(candidate.author_key, 0) + 1
        selected.append(candidate)
        selected.sort(key=lambda item: item.score, reverse=True)
        if len(selected) >= limit:
            break

    return FusionResult(
        drivers=selected[:limit],
        candidate_count=len(candidates),
        cluster_count=len(clusters),
    )
