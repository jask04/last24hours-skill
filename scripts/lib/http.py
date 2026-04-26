"""HTTP utilities for last24hours skill (stdlib only)."""

import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_TIMEOUT = 30
DEBUG = os.environ.get("LAST24HOURS_DEBUG", "").lower() in ("1", "true", "yes")

# Domain locks to serialize requests to sensitive APIs
_DOMAIN_LOCKS = {
    "kalshi.com": threading.Lock(),
    "scrapecreators.com": threading.Lock(),
}


def log(msg: str):
    """Log debug message to stderr."""
    if DEBUG:
        sys.stderr.write(f"[DEBUG] {msg}\n")
        sys.stderr.flush()
MAX_RETRIES = 5
MAX_429_RETRIES = 5
RETRY_DELAY = 2.0
USER_AGENT = "last24hours-skill/2.1 (Assistant Skill)"
_BROKEN_PROXY_VALUES = {"http://127.0.0.1:9", "http://localhost:9"}
_SECRET_QUERY_KEYS = {
    "api_key", "apikey", "key", "token", "access_token", "auth_token",
    "authorization", "password", "secret", "client_secret", "ct0",
}


class HTTPError(Exception):
    """HTTP request error with status code."""
    def __init__(self, message: str, status_code: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    max_429_retries: int = MAX_429_RETRIES,
    raw: bool = False,
) -> Dict[str, Any]:
    """Make an HTTP request and return JSON response.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        headers: Optional headers dict
        json_data: Optional JSON body (for POST)
        params: Optional query-string parameters
        timeout: Request timeout in seconds
        retries: Number of retries on failure
        max_429_retries: Maximum total attempts for HTTP 429 responses

    Returns:
        Parsed JSON response (or raw text if raw=True)

    Raises:
        HTTPError: On request failure
    """
    headers = headers or {}
    headers.setdefault("User-Agent", USER_AGENT)
    url = _append_params(url, params)

    data = None
    if json_data is not None:
        data = json.dumps(json_data).encode('utf-8')
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    log(f"{method} {_safe_url_for_log(url)}")

    # Find matching domain lock
    domain_lock = None
    url_lower = url.lower()
    for domain, lock in _DOMAIN_LOCKS.items():
        if domain in url_lower:
            domain_lock = lock
            break

    last_error = None
    for attempt in range(retries):
        try:
            opener = _get_url_opener()
            if domain_lock:
                with domain_lock:
                    with opener.open(req, timeout=timeout) as response:
                        body = response.read().decode('utf-8')
                        log(f"Response: {response.status} ({len(body)} bytes)")
                        if raw:
                            return body
                        return json.loads(body) if body else {}
            else:
                with opener.open(req, timeout=timeout) as response:
                    body = response.read().decode('utf-8')
                    log(f"Response: {response.status} ({len(body)} bytes)")
                    if raw:
                        return body
                    return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = None
            try:
                body = e.read().decode('utf-8')
            except Exception:
                pass
            log(f"HTTP Error {e.code}: {e.reason}")
            if body:
                snippet = " ".join(body.split())
                log(f"Error body: {snippet[:200]}")
            last_error = HTTPError(f"HTTP {e.code}: {e.reason}", e.code, body)

            # Don't retry client errors (4xx) except rate limits
            if 400 <= e.code < 500 and e.code != 429:
                raise last_error

            if e.code == 429 and attempt + 1 >= max_429_retries:
                raise last_error

            if attempt < retries - 1:
                if e.code == 429:
                    # Respect Retry-After header, fall back to exponential backoff
                    retry_after = e.headers.get("Retry-After") if hasattr(e, 'headers') else None
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = RETRY_DELAY * (2 ** attempt) + random.uniform(0.5, 2.0)
                    else:
                        delay = RETRY_DELAY * (2 ** attempt) + random.uniform(1.0, 3.0)
                    log(f"Rate limited (429). Waiting {delay:.1f}s before retry {attempt + 2}/{retries}")
                else:
                    delay = RETRY_DELAY * (2 ** attempt) + random.uniform(0.1, 1.0)
                time.sleep(delay)
        except urllib.error.URLError as e:
            log(f"URL Error: {e.reason}")
            last_error = HTTPError(f"URL Error: {e.reason}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1) + random.uniform(0.1, 1.0))
        except json.JSONDecodeError as e:
            log(f"JSON decode error: {e}")
            last_error = HTTPError(f"Invalid JSON response: {e}")
            raise last_error
        except (OSError, TimeoutError, ConnectionResetError) as e:
            # Handle socket-level errors (connection reset, timeout, etc.)
            log(f"Connection error: {type(e).__name__}: {e}")
            last_error = HTTPError(f"Connection error: {type(e).__name__}: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1) + random.uniform(0.1, 1.0))

    if last_error:
        raise last_error
    raise HTTPError("Request failed with no error details")


def _get_url_opener():
    """Bypass obviously broken localhost proxy traps in desktop environments."""
    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
    proxy_values = {
        os.environ.get(name, "").strip().lower()
        for name in proxy_names
        if os.environ.get(name)
    }
    if proxy_values and proxy_values.issubset(_BROKEN_PROXY_VALUES):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _append_params(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    clean_params = {key: value for key, value in params.items() if value is not None}
    if not clean_params:
        return url
    separator = "&" if urllib.parse.urlsplit(url).query else "?"
    return f"{url}{separator}{urllib.parse.urlencode(clean_params, doseq=True)}"


def _safe_url_for_log(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "[REDACTED]" if key.lower() in _SECRET_QUERY_KEYS else value)
        for key, value in pairs
    ]
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(redacted, doseq=True)))


def get(url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Make a GET request."""
    return request("GET", url, headers=headers, **kwargs)


def post(url: str, json_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Make a POST request with JSON body."""
    return request("POST", url, headers=headers, json_data=json_data, **kwargs)


def post_raw(url: str, json_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None, **kwargs) -> str:
    """Make a POST request with JSON body and return raw text."""
    return request("POST", url, headers=headers, json_data=json_data, raw=True, **kwargs)


def scrapecreators_headers(token: str) -> Dict[str, str]:
    """Build ScrapeCreators request headers."""
    return {
        "x-api-key": token,
        "Content-Type": "application/json",
    }


def get_reddit_json(path: str, timeout: int = DEFAULT_TIMEOUT, retries: int = MAX_RETRIES) -> Dict[str, Any]:
    """Fetch Reddit thread JSON.

    Args:
        path: Reddit path (e.g., /r/subreddit/comments/id/title)
        timeout: HTTP timeout per attempt in seconds
        retries: Number of retries on failure

    Returns:
        Parsed JSON response
    """
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path

    # Remove trailing slash and add .json
    path = path.rstrip('/')
    if not path.endswith('.json'):
        path = path + '.json'

    url = f"https://www.reddit.com{path}?raw_json=1"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    return get(url, headers=headers, timeout=timeout, retries=retries)
