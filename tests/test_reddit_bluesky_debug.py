import unittest
from unittest import mock

from scripts import last24hours
from scripts.lib import bluesky, http, openai_reddit, render


class RedditBlueskyDebugTests(unittest.TestCase):
    def test_disabled_scrapecreators_never_calls_reddit_paid_path(self):
        config = {
            "SCRAPECREATORS_API_KEY": "stored-but-disabled",
            "LAST24HOURS_DISABLE_SCRAPECREATORS": "1",
        }
        with mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=[]), \
             mock.patch("scripts.last24hours.reddit.search_and_enrich") as paid_search:
            items, _, error, used_sc = last24hours._search_reddit(
                "obscure topic",
                config,
                {"openai": "gpt-test"},
                "2026-04-10",
                "2026-04-11",
                "default",
                False,
            )

        self.assertEqual(items, [])
        self.assertIsNone(error)
        self.assertFalse(used_sc)
        paid_search.assert_not_called()

    def test_scrapecreators_payment_error_preserves_public_reddit_results(self):
        public_items = [
            {
                "id": "R1",
                "title": "NBA injury update",
                "url": "https://www.reddit.com/r/nba/comments/abc/injury/",
                "subreddit": "nba",
                "relevance": 0.8,
            }
        ]
        config = {
            "SCRAPECREATORS_API_KEY": "enabled",
            "LAST24HOURS_DISABLE_SCRAPECREATORS": "0",
        }
        with mock.patch("scripts.last24hours.openai_reddit.search_reddit_public", return_value=public_items), \
             mock.patch(
                 "scripts.last24hours.reddit.search_and_enrich",
                 return_value={"items": [], "error": "ScrapeCreators payment required"},
             ):
            items, _, error, used_sc = last24hours._search_reddit(
                "NBA",
                config,
                {"openai": "gpt-test"},
                "2026-04-10",
                "2026-04-11",
                "default",
                False,
            )

        self.assertEqual(items, public_items)
        self.assertIsNone(error)
        self.assertFalse(used_sc)

    def test_source_health_counters_serialize_blocked_and_empty_buckets(self):
        report = last24hours.schema.Report(
            topic="Fed rate cut by June",
            range_from="2026-04-10",
            range_to="2026-04-11",
            generated_at="2026-04-11T00:00:00Z",
            mode="both",
        )
        report.forecasts = [
            last24hours.schema.ForecastItem(
                title="Fed rate cut by June",
                model_implied=True,
            )
        ]

        last24hours._populate_source_health(
            report,
            "prediction",
            {"source_status": "blocked", "blocked_attempts": 2, "error": "HTTP 403: Blocked"},
        )

        payload = report.to_dict()["evidence_fusion_stats"]["source_health"]
        self.assertEqual(payload["blocked_reddit_public_attempts"], 2)
        self.assertEqual(payload["source_status"]["reddit"]["status"], "blocked")
        self.assertEqual(payload["empty_source_buckets"]["x"], 1)
        self.assertEqual(payload["empty_source_buckets"]["web"], 1)
        self.assertEqual(payload["degraded_prediction_runs"]["macro"], 1)

    def test_source_health_serializes_x_and_web_degraded_statuses(self):
        report = last24hours.schema.Report(
            topic="Bitcoin above 100k this week",
            range_from="2026-04-10",
            range_to="2026-04-11",
            generated_at="2026-04-11T00:00:00Z",
            mode="both",
        )
        report.forecasts = [
            last24hours.schema.ForecastItem(
                title="Bitcoin above 100k this week",
                model_implied=True,
            )
        ]
        report.x_error = "HTTP 429: Too Many Requests"
        report.web_error = "timed out contacting web search"

        last24hours._populate_source_health(report, "prediction", None)

        payload = report.to_dict()["evidence_fusion_stats"]["source_health"]
        self.assertEqual(payload["source_status"]["x"]["status"], "degraded")
        self.assertEqual(payload["source_status"]["web"]["status"], "degraded")
        self.assertEqual(payload["degraded_source_buckets"]["x"], 1)
        self.assertEqual(payload["degraded_source_buckets"]["web"], 1)

    def test_source_health_serializes_kalshi_empty_and_render_footer(self):
        report = last24hours.schema.Report(
            topic="Fed rate cut by June",
            range_from="2026-04-10",
            range_to="2026-04-11",
            generated_at="2026-04-11T00:00:00Z",
            mode="kalshi",
        )
        report.forecasts = [
            last24hours.schema.ForecastItem(
                title="Fed rate cut by June",
                model_implied=True,
            )
        ]

        last24hours._populate_source_health(report, "prediction", None)

        payload = report.to_dict()["evidence_fusion_stats"]["source_health"]
        self.assertEqual(payload["source_status"]["kalshi"]["status"], "empty")
        self.assertIn("no compatible Kalshi contract", payload["source_status"]["kalshi"]["detail"])
        footer = render.render_source_status(report, {"source_status": payload["source_status"]})
        self.assertIn("NORESULT Kalshi", footer)

    def test_source_health_serializes_kalshi_degraded_status(self):
        report = last24hours.schema.Report(
            topic="Fed rate cut by June",
            range_from="2026-04-10",
            range_to="2026-04-11",
            generated_at="2026-04-11T00:00:00Z",
            mode="kalshi",
        )
        report.forecasts = [
            last24hours.schema.ForecastItem(
                title="Fed rate cut by June",
                model_implied=True,
            )
        ]
        report.kalshi_error = "Kalshi search timed out after 12s"

        last24hours._populate_source_health(report, "prediction", None)

        payload = report.to_dict()["evidence_fusion_stats"]["source_health"]
        self.assertEqual(payload["source_status"]["kalshi"]["status"], "degraded")
        self.assertEqual(payload["degraded_source_buckets"]["kalshi"], 1)

    def test_disabled_scrapecreators_gates_legacy_x_paid_path(self):
        config = {
            "SCRAPECREATORS_API_KEY": "stored-but-disabled",
            "LAST24HOURS_DISABLE_SCRAPECREATORS": "1",
        }
        with mock.patch("scripts.last24hours.scrapecreators_x.search_x") as paid_x:
            items, raw, error = last24hours._search_x(
                "NBA",
                config,
                {"xai": "grok-test"},
                "2026-04-10",
                "2026-04-11",
                "quick",
                False,
                x_source="scrapecreators",
            )

        self.assertEqual(items, [])
        self.assertEqual(raw.get("error"), "ScrapeCreators disabled by LAST24HOURS_DISABLE_SCRAPECREATORS")
        self.assertEqual(error, "ScrapeCreators disabled by LAST24HOURS_DISABLE_SCRAPECREATORS")
        paid_x.assert_not_called()

    def test_auxiliary_only_search_sources_do_not_route_to_web(self):
        self.assertEqual(last24hours.sources_mode_for_explicit_search({"bluesky"}), "none")
        self.assertEqual(last24hours.sources_mode_for_explicit_search({"bsky"}), "none")
        self.assertEqual(last24hours.sources_mode_for_explicit_search({"bluesky", "web"}), "web")
        self.assertEqual(last24hours.sources_mode_for_explicit_search({"reddit", "bluesky"}), "reddit")
        self.assertEqual(last24hours.mode_label_for_sources("none"), "auxiliary-only")

    def test_bluesky_public_403_can_fall_back_to_auth(self):
        bluesky._cached_token = None
        bluesky._session_error = None

        def fake_request(method, url, **kwargs):
            if "public.api.bsky.app" in url:
                raise http.HTTPError("HTTP 403: Forbidden", status_code=403, body="Forbidden")
            if "createSession" in url:
                return {"accessJwt": "token"}
            if "bsky.social/xrpc/app.bsky.feed.searchPosts" in url:
                return {"posts": [{"uri": "at://did/app.bsky.feed.post/rkey", "record": {"text": "NBA lineup news"}, "author": {"handle": "example.bsky.social"}}]}
            raise AssertionError(f"unexpected URL {url}")

        with mock.patch("scripts.lib.bluesky.http.request", side_effect=fake_request):
            response = bluesky.search_bluesky(
                "NBA",
                "2026-04-10",
                "2026-04-11",
                depth="quick",
                config={"BSKY_HANDLE": "example.bsky.social", "BSKY_APP_PASSWORD": "app-pass"},
            )

        self.assertEqual(len(response.get("posts", [])), 1)
        self.assertNotIn("error", response)

    def test_bluesky_public_and_auth_403_reports_non_credential_warning(self):
        bluesky._cached_token = None
        bluesky._session_error = None

        def fake_request(method, url, **kwargs):
            if "public.api.bsky.app" in url:
                raise http.HTTPError("HTTP 403: Forbidden", status_code=403, body="Forbidden")
            if "createSession" in url:
                return {"accessJwt": "token"}
            if "bsky.social/xrpc/app.bsky.feed.searchPosts" in url:
                raise http.HTTPError("HTTP 403: Forbidden", status_code=403, body="Forbidden")
            raise AssertionError(f"unexpected URL {url}")

        with mock.patch("scripts.lib.bluesky.http.request", side_effect=fake_request):
            response = bluesky.search_bluesky(
                "NBA",
                "2026-04-10",
                "2026-04-11",
                depth="quick",
                config={"BSKY_HANDLE": "example.bsky.social", "BSKY_APP_PASSWORD": "app-pass"},
            )

        self.assertEqual(response.get("posts"), [])
        self.assertIn("Bluesky public search forbidden (403)", response.get("error", ""))
        self.assertIn("not enough by itself to prove the app password is bad", response.get("error", ""))

    def test_broad_nba_reddit_quality_filter_suppresses_incidental_matches(self):
        self.assertFalse(openai_reddit._subreddit_quality_ok("Torontobluejays", "NBA"))
        self.assertTrue(openai_reddit._subreddit_quality_ok("nba", "NBA"))
        self.assertTrue(openai_reddit._is_low_signal_broad_nba_item("NBA", "NBA research form", "nba"))
        self.assertFalse(openai_reddit._is_low_signal_broad_nba_item("NBA", "NBA injury update", "nba"))


if __name__ == "__main__":
    unittest.main()
