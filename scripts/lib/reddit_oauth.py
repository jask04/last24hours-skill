"""Official Reddit OAuth search/enrichment for last24hours."""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from . import dates, http, openai_reddit, reddit_enrich, sports_schedule

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE = "https://oauth.reddit.com"

_cached_token: Optional[str] = None
_cached_token_expires_at: float = 0.0
_last_rate_remaining: Optional[float] = None
_last_rate_reset: Optional[float] = None


def is_configured(config: Dict[str, Any]) -> bool:
    return bool(
        config.get("REDDIT_CLIENT_ID")
        and config.get("REDDIT_CLIENT_SECRET")
        and config.get("REDDIT_USER_AGENT")
    )


def reset_cache() -> None:
    global _cached_token, _cached_token_expires_at, _last_rate_remaining, _last_rate_reset
    _cached_token = None
    _cached_token_expires_at = 0.0
    _last_rate_remaining = None
    _last_rate_reset = None


def get_access_token(config: Dict[str, Any]) -> str:
    """Fetch or return a cached app-only OAuth token."""
    global _cached_token, _cached_token_expires_at
    now = time.time()
    if _cached_token and _cached_token_expires_at > now + 60:
        return _cached_token
    if not is_configured(config):
        raise http.HTTPError("Reddit OAuth credentials are not configured")

    client_id = str(config.get("REDDIT_CLIENT_ID") or "")
    client_secret = str(config.get("REDDIT_CLIENT_SECRET") or "")
    user_agent = str(config.get("REDDIT_USER_AGENT") or http.USER_AGENT)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "User-Agent": user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with http._get_url_opener().open(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise http.HTTPError(f"Reddit OAuth token HTTP {e.code}: {e.reason}", e.code, body) from e
    except Exception as e:
        raise http.HTTPError(f"Reddit OAuth token error: {type(e).__name__}: {e}") from e

    token = payload.get("access_token")
    if not token:
        raise http.HTTPError("Reddit OAuth token response missing access_token")
    _cached_token = token
    _cached_token_expires_at = now + int(payload.get("expires_in") or 3600)
    return token


def _rate_limited_preflight() -> None:
    if _last_rate_remaining is not None and _last_rate_remaining <= 1:
        reset_hint = f"; reset in {_last_rate_reset:g}s" if _last_rate_reset is not None else ""
        raise http.HTTPError(f"Reddit OAuth rate limit nearly exhausted{reset_hint}", 429)


def _oauth_get(path: str, config: Dict[str, Any], params: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Any:
    """GET a Reddit OAuth endpoint and return JSON."""
    global _last_rate_remaining, _last_rate_reset
    _rate_limited_preflight()
    token = get_access_token(config)
    user_agent = str(config.get("REDDIT_USER_AGENT") or http.USER_AGENT)
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{OAUTH_BASE}{path}{query}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent, "Accept": "application/json"},
    )
    try:
        with http._get_url_opener().open(req, timeout=timeout) as response:
            headers = response.info()
            remaining = headers.get("x-ratelimit-remaining")
            reset = headers.get("x-ratelimit-reset")
            _last_rate_remaining = float(remaining) if remaining is not None else _last_rate_remaining
            _last_rate_reset = float(reset) if reset is not None else _last_rate_reset
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise http.HTTPError(f"Reddit OAuth HTTP {e.code}: {e.reason}", e.code, body) from e
    except Exception as e:
        raise http.HTTPError(f"Reddit OAuth request error: {type(e).__name__}: {e}") from e


def _date_from_post(post: Dict[str, Any]) -> Optional[str]:
    created_utc = post.get("created_utc")
    return dates.timestamp_to_date(created_utc) if created_utc else None


def _post_to_item(post: Dict[str, Any], topic: str, source_label: str, item_id: str) -> Optional[Dict[str, Any]]:
    permalink = str(post.get("permalink", "")).strip()
    if not permalink or "/comments/" not in permalink:
        return None
    title = str(post.get("title", "")).strip()
    subreddit = str(post.get("subreddit", "")).strip()
    if not openai_reddit._subreddit_quality_ok(subreddit, topic):
        return None
    if openai_reddit._is_low_signal_broad_nba_item(topic, title, subreddit):
        return None
    if not openai_reddit._matches_matchup_topic(topic, title, subreddit):
        return None
    topic_relevance = openai_reddit._public_topic_relevance(topic, title, subreddit)
    if topic_relevance < 0.22:
        return None

    score = int(post.get("score", 0) or 0)
    num_comments = int(post.get("num_comments", 0) or 0)
    relevance = round(
        max(0.0, min(1.0, 0.65 * topic_relevance + 0.35 * openai_reddit._public_relevance(score, num_comments) + openai_reddit._sports_public_item_bonus(topic, title, subreddit))),
        3,
    )
    return {
        "id": item_id,
        "title": title,
        "url": f"https://www.reddit.com{permalink}",
        "subreddit": subreddit,
        "date": _date_from_post(post),
        "why_relevant": source_label,
        "relevance": relevance,
        "engagement": {"score": score, "num_comments": num_comments, "upvote_ratio": post.get("upvote_ratio")},
    }


def _parse_listing(data: Dict[str, Any], topic: str, source_label: str, seen_urls: set, start_index: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    children = data.get("data", {}).get("children", []) if isinstance(data, dict) else []
    for child in children:
        if child.get("kind") != "t3":
            continue
        post = child.get("data", {})
        permalink = str(post.get("permalink", "")).strip()
        full_url = f"https://www.reddit.com{permalink}" if permalink else ""
        if not full_url or full_url in seen_urls:
            continue
        item = _post_to_item(post, topic, source_label, f"R{start_index + len(items)}")
        if item:
            seen_urls.add(full_url)
            items.append(item)
    return items


def search_reddit_oauth(topic: str, from_date: str, to_date: str, depth: str = "default", config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Search Reddit via OAuth and return raw items in the public Reddit shape."""
    config = config or {}
    _, max_items = openai_reddit.DEPTH_CONFIG.get(depth, openai_reddit.DEPTH_CONFIG["default"])
    limit = min(100, max(20, max_items))
    core = openai_reddit._extract_core_subject(topic)
    queries = [topic]
    if core and core.lower() != topic.lower():
        queries.extend([core, f'"{core}"'])

    seen_urls = set()
    all_items: List[Dict[str, Any]] = []
    try:
        for query in queries:
            data = _oauth_get("/search", config, params={"q": query, "sort": "new", "t": "month", "limit": limit, "raw_json": 1}, timeout=20)
            all_items.extend(_parse_listing(data, topic, "Found via Reddit OAuth search", seen_urls, len(all_items) + 1))

        for sub in sports_schedule.matchup_subreddits(topic)[:4]:
            data = _oauth_get(f"/r/{sub}/search", config, params={"q": core or topic, "restrict_sr": "on", "sort": "new", "limit": min(25, limit), "raw_json": 1}, timeout=15)
            all_items.extend(_parse_listing(data, topic, f"Found via r/{sub} Reddit OAuth search", seen_urls, len(all_items) + 1))
    except Exception as e:
        return {"source": "reddit_oauth", "items": all_items, "error": f"{type(e).__name__}: {e}", "rate_remaining": _last_rate_remaining, "rate_reset": _last_rate_reset}

    all_items.sort(key=lambda item: (item.get("date") or "", float(item.get("relevance", 0.0))), reverse=True)
    return {"source": "reddit_oauth", "items": all_items[: max_items * 2], "rate_remaining": _last_rate_remaining, "rate_reset": _last_rate_reset}


def fetch_thread_data(url: str, config: Dict[str, Any], timeout: int = 10) -> Any:
    """Fetch a Reddit thread via OAuth using the existing Reddit URL."""
    path = reddit_enrich.extract_reddit_path(url)
    if not path:
        return None
    path = path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    return _oauth_get(path, config, params={"raw_json": 1}, timeout=timeout)
