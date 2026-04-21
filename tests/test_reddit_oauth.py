import json
import unittest
from unittest import mock

from scripts import last24hours
from scripts.lib import env, reddit_oauth


class _FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def info(self):
        return self.headers


class _FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        return self.responses.pop(0)


class RedditOAuthTests(unittest.TestCase):
    def setUp(self):
        reddit_oauth.reset_cache()

    def test_oauth_token_success_caches_and_uses_bearer_header(self):
        config = {
            "REDDIT_CLIENT_ID": "client",
            "REDDIT_CLIENT_SECRET": "secret",
            "REDDIT_USER_AGENT": "last24hours-test",
        }
        opener = _FakeOpener([
            _FakeResponse({"access_token": "token-1", "expires_in": 3600}),
            _FakeResponse({"data": {"children": []}}, {"x-ratelimit-remaining": "42", "x-ratelimit-reset": "600"}),
            _FakeResponse({"data": {"children": []}}, {"x-ratelimit-remaining": "41", "x-ratelimit-reset": "599"}),
        ])

        with mock.patch("scripts.lib.reddit_oauth.http._get_url_opener", return_value=opener):
            token = reddit_oauth.get_access_token(config)
            reddit_oauth._oauth_get("/search", config, params={"q": "NBA"})
            reddit_oauth._oauth_get("/search", config, params={"q": "NBA"})

        self.assertEqual(token, "token-1")
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(opener.requests[1].headers.get("Authorization"), "Bearer token-1")
        self.assertEqual(opener.requests[2].headers.get("Authorization"), "Bearer token-1")

    def test_oauth_search_results_match_public_reddit_shape(self):
        post = {
            "kind": "t3",
            "data": {
                "title": "NBA injury update",
                "permalink": "/r/nba/comments/abc/injury/",
                "subreddit": "nba",
                "score": 10,
                "num_comments": 5,
                "created_utc": 1775865600,
            },
        }
        with mock.patch(
            "scripts.lib.reddit_oauth._oauth_get",
            return_value={"data": {"children": [post]}},
        ):
            result = reddit_oauth.search_reddit_oauth(
                "NBA",
                "2026-04-10",
                "2026-04-11",
                depth="quick",
                config={"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "sec", "REDDIT_USER_AGENT": "ua"},
            )

        self.assertEqual(result["source"], "reddit_oauth")
        self.assertEqual(result["items"][0]["title"], "NBA injury update")
        self.assertEqual(result["items"][0]["subreddit"], "nba")
        self.assertIn("engagement", result["items"][0])

    def test_auto_oauth_failure_falls_back_to_public_json(self):
        public_items = [{"id": "R1", "title": "NBA injury update", "url": "https://www.reddit.com/r/nba/comments/abc/injury/", "subreddit": "nba"}]
        config = {
            "REDDIT_CLIENT_ID": "id",
            "REDDIT_CLIENT_SECRET": "sec",
            "REDDIT_USER_AGENT": "ua",
            "LAST24HOURS_REDDIT_SOURCE": "auto",
        }
        with mock.patch("scripts.last24hours.reddit_oauth.search_reddit_oauth", return_value={"source": "reddit_oauth", "items": [], "error": "HTTP 429"}), \
             mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=public_items):
            items, raw, error, used_sc = last24hours._search_reddit(
                "NBA", config, {"openai": "gpt-test"}, "2026-04-10", "2026-04-11", "quick", False,
            )

        self.assertEqual(items, public_items)
        self.assertEqual(raw["source"], "reddit_public")
        self.assertIn("Reddit OAuth failed", raw["warning"])
        self.assertIsNone(error)
        self.assertFalse(used_sc)

    def test_public_source_never_calls_oauth(self):
        config = {
            "REDDIT_CLIENT_ID": "id",
            "REDDIT_CLIENT_SECRET": "sec",
            "REDDIT_USER_AGENT": "ua",
            "LAST24HOURS_REDDIT_SOURCE": "public",
        }
        with mock.patch("scripts.last24hours.reddit_oauth.search_reddit_oauth") as oauth_search, \
             mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=[]):
            last24hours._search_reddit(
                "NBA", config, {"openai": "gpt-test"}, "2026-04-10", "2026-04-11", "quick", False,
            )

        oauth_search.assert_not_called()

    def test_auto_source_reports_public_when_oauth_missing(self):
        self.assertEqual(env.get_reddit_source({"LAST24HOURS_REDDIT_SOURCE": "auto"}), "public")

    def test_oauth_source_attempts_oauth_and_reports_fallback_warning(self):
        config = {
            "REDDIT_CLIENT_ID": "id",
            "REDDIT_CLIENT_SECRET": "sec",
            "REDDIT_USER_AGENT": "ua",
            "LAST24HOURS_REDDIT_SOURCE": "oauth",
        }
        with mock.patch("scripts.last24hours.reddit_oauth.search_reddit_oauth", return_value={"source": "reddit_oauth", "items": [], "error": "HTTP 403"}), \
             mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=[]):
            items, raw, error, _ = last24hours._search_reddit(
                "NBA", config, {"openai": "gpt-test"}, "2026-04-10", "2026-04-11", "quick", False,
            )

        self.assertEqual(items, [])
        self.assertEqual(raw["source"], "reddit_public")
        self.assertIn("Reddit OAuth failed", raw["warning"])
        self.assertIn("HTTP 403", error)

    def test_oauth_source_without_credentials_reports_fallback_warning(self):
        config = {"LAST24HOURS_REDDIT_SOURCE": "oauth"}
        with mock.patch("scripts.last24hours.reddit_oauth.search_reddit_oauth") as oauth_search, \
             mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=[]):
            _, raw, error, _ = last24hours._search_reddit(
                "NBA", config, {"openai": "gpt-test"}, "2026-04-10", "2026-04-11", "quick", False,
            )

        oauth_search.assert_not_called()
        self.assertEqual(raw["source"], "reddit_public")
        self.assertIn("credentials are not configured", raw["warning"])
        self.assertIn("credentials are not configured", error)

    def test_public_source_blocked_sets_blocked_status(self):
        config = {"LAST24HOURS_REDDIT_SOURCE": "public"}
        with mock.patch(
            "scripts.last24hours.openai_reddit.search_reddit_public",
            return_value=([], {"source": "reddit_public", "status": "blocked", "blocked_attempts": 2, "errors": ["HTTP 403: Blocked"]}),
        ):
            items, raw, error, _ = last24hours._search_reddit(
                "Fed rate cut by June", config, {"openai": "gpt-test"}, "2026-04-10", "2026-04-11", "quick", False,
            )

        self.assertEqual(items, [])
        self.assertEqual(raw["source_status"], "blocked")
        self.assertEqual(raw["blocked_attempts"], 2)
        self.assertIn("blocked", error.lower())

    def test_oauth_rate_limit_preflight_stops_additional_calls(self):
        config = {
            "REDDIT_CLIENT_ID": "client",
            "REDDIT_CLIENT_SECRET": "secret",
            "REDDIT_USER_AGENT": "last24hours-test",
        }
        opener = _FakeOpener([
            _FakeResponse({"access_token": "token-1", "expires_in": 3600}),
            _FakeResponse(
                {"data": {"children": []}},
                {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "600"},
            ),
        ])
        with mock.patch("scripts.lib.reddit_oauth.http._get_url_opener", return_value=opener):
            reddit_oauth._oauth_get("/search", config, params={"q": "NBA"})
            with self.assertRaises(Exception) as ctx:
                reddit_oauth._oauth_get("/search", config, params={"q": "NBA"})

        self.assertIn("rate limit nearly exhausted", str(ctx.exception))
        self.assertEqual(len(opener.requests), 2)

    def test_oauth_thread_fetch_enriches_via_existing_parser(self):
        thread_data = [
            {"data": {"children": [{"data": {"score": 12, "num_comments": 2, "upvote_ratio": 0.9, "created_utc": 1775865600, "title": "NBA injury update"}}]}},
            {"data": {"children": [{"kind": "t1", "data": {"body": "Meaningful lineup note for this NBA game.", "score": 4, "author": "fan", "created_utc": 1775865600, "permalink": "/r/nba/comments/abc/_/def/"}}]}},
        ]
        item = {"url": "https://www.reddit.com/r/nba/comments/abc/injury/", "title": "NBA injury update"}
        with mock.patch("scripts.last24hours.reddit_oauth.fetch_thread_data", return_value=thread_data):
            enriched = last24hours._enrich_reddit_item_free(
                item,
                {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "sec", "REDDIT_USER_AGENT": "ua"},
                timeout=5,
                retries=1,
            )

        self.assertEqual(enriched["engagement"]["score"], 12)
        self.assertEqual(enriched["top_comments"][0]["score"], 4)


if __name__ == "__main__":
    unittest.main()
