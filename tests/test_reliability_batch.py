import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from scripts import evaluate_search_quality, last24hours, store
from scripts.lib import bluesky, dates, http, sports_schedule, weather


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    status = 200

    def __init__(self, body='{"ok": true}'):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body.encode("utf-8")


class _Opener:
    def __init__(self, side_effect):
        self.open = mock.Mock(side_effect=side_effect)


class EvalFixtureTests(unittest.TestCase):
    def test_default_eval_topics_load_from_fixture(self):
        topics = evaluate_search_quality.load_eval_topics()

        self.assertEqual(
            topics,
            [
                ("tomorrows nba games", "prediction"),
                ("NBA markets to watch today", "market_watchlist"),
                ("NBA paper bundle today", "market_watchlist"),
                ("NBA paper bundle tomorrow", "market_watchlist"),
                ("Bitcoin above 100k this week", "prediction"),
                ("Fed rate cut by June", "prediction"),
                ("NYC rain tomorrow", "prediction"),
                ("AI coding tools markets to watch today", "market_watchlist"),
                ("Polymarket markets closing soon", "market_watchlist"),
                ("crypto markets closing soon tonight", "market_watchlist"),
            ],
        )

    def test_load_eval_topics_ignores_blank_topic_and_defaults_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.json"
            path.write_text(
                json.dumps([
                    {"topic": "", "query_type": "prediction"},
                    {"topic": "custom market"},
                ]),
                encoding="utf-8",
            )

            self.assertEqual(evaluate_search_quality.load_eval_topics(path), [("custom market", "custom")])

    def test_eval_default_baseline_is_origin_master(self):
        with mock.patch.object(sys, "argv", ["evaluate_search_quality.py"]):
            args = evaluate_search_quality.parse_args()

        self.assertEqual(args.baseline_rev, "origin/master")

    def test_no_default_topics_plus_custom_topic(self):
        with mock.patch.object(sys, "argv", ["evaluate_search_quality.py", "--no-default-topics", "--topic", "custom"]):
            args = evaluate_search_quality.parse_args()

        topics = [] if args.no_default_topics else evaluate_search_quality.load_eval_topics()
        topics.extend((topic, "custom") for topic in args.topic)
        self.assertEqual(topics, [("custom", "custom")])


class DateAndCleanupTests(unittest.TestCase):
    def test_as_of_date_controls_relative_nba_and_weather_dates(self):
        with mock.patch.dict(os.environ, {"LAST24HOURS_AS_OF_DATE": "2026-04-19"}):
            self.assertEqual(dates.get_date_range(1), ("2026-04-18", "2026-04-19"))
            self.assertEqual(sports_schedule.resolve_relative_nba_date("NBA matchups tomorrow"), "20260420")
            self.assertEqual(weather._target_date("NYC rain tomorrow"), "2026-04-20")

    def test_cleanup_saved_reports_deletes_only_old_raw_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_report = root / "btc-raw.md"
            new_report = root / "nba-raw.md"
            other_markdown = root / "notes.md"
            old_report.write_text("old", encoding="utf-8")
            new_report.write_text("new", encoding="utf-8")
            other_markdown.write_text("keep", encoding="utf-8")
            old_time = time.time() - (3 * 86400)
            os.utime(old_report, (old_time, old_time))

            deleted = last24hours.cleanup_saved_reports(root, retention_days=1)

            self.assertEqual(deleted, 1)
            self.assertFalse(old_report.exists())
            self.assertTrue(new_report.exists())
            self.assertTrue(other_markdown.exists())


class HttpHelperTests(unittest.TestCase):
    def _request_url(self, opener):
        return opener.open.call_args[0][0].full_url

    def test_params_append_to_clean_url(self):
        opener = _Opener([_Response()])

        with mock.patch("scripts.lib.http._get_url_opener", return_value=opener):
            http.get("https://api.example.com/search", params={"q": "NBA finals", "limit": 10})

        sent_url = self._request_url(opener)
        self.assertTrue(sent_url.startswith("https://api.example.com/search?"))
        self.assertIn("q=NBA+finals", sent_url)
        self.assertIn("limit=10", sent_url)

    def test_params_append_to_existing_query_string(self):
        opener = _Opener([_Response()])

        with mock.patch("scripts.lib.http._get_url_opener", return_value=opener):
            http.get("https://api.example.com/search?existing=1", params={"q": "BTC"})

        self.assertEqual(self._request_url(opener), "https://api.example.com/search?existing=1&q=BTC")

    def test_none_params_are_omitted(self):
        opener = _Opener([_Response()])

        with mock.patch("scripts.lib.http._get_url_opener", return_value=opener):
            http.get("https://api.example.com/search", params={"q": "BTC", "cursor": None})

        sent_url = self._request_url(opener)
        self.assertIn("q=BTC", sent_url)
        self.assertNotIn("cursor", sent_url)

    def test_429_retries_are_capped(self):
        error = urllib.error.HTTPError("https://api.example.com", 429, "Too Many Requests", {}, None)
        opener = _Opener([error, error, error, error, error])

        with mock.patch("scripts.lib.http._get_url_opener", return_value=opener), \
             mock.patch("scripts.lib.http.time.sleep"):
            with self.assertRaises(http.HTTPError):
                http.get("https://api.example.com", retries=5)

        self.assertEqual(opener.open.call_count, 5)

    def test_500_errors_use_full_retry_count(self):
        error = urllib.error.HTTPError("https://api.example.com", 500, "Server Error", {}, None)
        opener = _Opener([error, error, error])

        with mock.patch("scripts.lib.http._get_url_opener", return_value=opener), \
             mock.patch("scripts.lib.http.time.sleep"):
            with self.assertRaises(http.HTTPError):
                http.get("https://api.example.com", retries=3)

        self.assertEqual(opener.open.call_count, 3)

    def test_scrapecreators_headers_are_consistent(self):
        self.assertEqual(
            http.scrapecreators_headers("token"),
            {"x-api-key": "token", "Content-Type": "application/json"},
        )

    def test_debug_url_redacts_secret_query_values(self):
        redacted = http._safe_url_for_log("https://api.example.com/search?api_key=secret&q=btc&ct0=csrf")

        self.assertIn("api_key=%5BREDACTED%5D", redacted)
        self.assertIn("ct0=%5BREDACTED%5D", redacted)
        self.assertIn("q=btc", redacted)
        self.assertNotIn("secret", redacted)
        self.assertNotIn("csrf", redacted)


class StoreHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_override = store._db_override
        store._db_override = Path(self.tmp.name) / "research.db"
        store.init_db()

    def tearDown(self):
        store._db_override = self.previous_override
        self.tmp.cleanup()

    def test_update_helpers_accept_valid_fields_and_reject_invalid_fields(self):
        topic = store.add_topic("Test Topic")
        run_id = store.record_run(topic["id"], source_mode="both")

        store.update_run(run_id, status="failed")

        store.store_findings(run_id, topic["id"], [{
            "source": "reddit",
            "url": "https://example.com/item",
            "title": "Finding",
            "content": "content",
        }])
        conn = sqlite3.connect(str(store._db_override))
        finding_id = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()[0]
        conn.close()

        store.update_finding(finding_id, dismissed=1)

        with self.assertRaisesRegex(ValueError, "invalid_run_column"):
            store.update_run(run_id, invalid_run_column="x")
        with self.assertRaisesRegex(ValueError, "invalid_finding_column"):
            store.update_finding(finding_id, invalid_finding_column="x")


class BlueskyTokenCacheTests(unittest.TestCase):
    def tearDown(self):
        bluesky._reset_session_cache()

    def test_fresh_cached_token_is_reused(self):
        bluesky._cached_token = "cached"
        bluesky._token_created_at = 100.0

        with mock.patch("scripts.lib.bluesky.time.monotonic", return_value=200.0), \
             mock.patch("scripts.lib.bluesky.http.request") as request:
            token = bluesky._create_session("example.bsky.social", "app-pass")

        self.assertEqual(token, "cached")
        request.assert_not_called()

    def test_expired_cached_token_is_replaced(self):
        bluesky._cached_token = "old"
        bluesky._token_created_at = 100.0

        with mock.patch("scripts.lib.bluesky.time.monotonic", side_effect=[5601.0, 5601.0]), \
             mock.patch("scripts.lib.bluesky.http.request", return_value={"accessJwt": "new"}) as request:
            token = bluesky._create_session("example.bsky.social", "app-pass")

        self.assertEqual(token, "new")
        self.assertEqual(bluesky._cached_token, "new")
        request.assert_called_once()

    def test_reset_session_cache_clears_token_timestamp_and_error(self):
        bluesky._cached_token = "cached"
        bluesky._token_created_at = 123.0
        bluesky._session_error = "error"

        bluesky._reset_session_cache()

        self.assertIsNone(bluesky._cached_token)
        self.assertEqual(bluesky._token_created_at, 0.0)
        self.assertIsNone(bluesky._session_error)


class VersionConsistencyTests(unittest.TestCase):
    def _skill_version(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r'^version:\s*"([^"]+)"\s*$', text, re.MULTILINE)
        if not match:
            raise AssertionError("SKILL.md version frontmatter not found")
        return match.group(1)

    def test_version_surfaces_match_skill_frontmatter(self):
        version = self._skill_version()

        self.assertIn(f"# last24hours v{version}:", (ROOT / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "README.md").read_text(encoding="utf-8").startswith(f"# /last24hours v{version}"))
        self.assertEqual(json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"], version)
        self.assertEqual(json.loads((ROOT / "gemini-extension.json").read_text(encoding="utf-8"))["version"], version)

        ui_text = (ROOT / "scripts" / "lib" / "ui.py").read_text(encoding="utf-8")
        self.assertIn(f"/last24hours v{version} — Source Status", ui_text)
        self.assertEqual(ui_text.count(f"/last24hours v{version} — Source Status"), 2)

    def test_adapter_version_strings_match_skill_frontmatter(self):
        version = self._skill_version()

        for relative in ("scripts/lib/bird_x.py", "scripts/lib/youtube_yt.py"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            match = re.search(r"v(\d+\.\d+\.\d+)", text)
            self.assertIsNotNone(match, relative)
            self.assertEqual(match.group(1), version)

    def test_current_version_surfaces_do_not_keep_previous_version(self):
        version = self._skill_version()
        major, minor, patch = [int(part) for part in version.split(".")]
        if patch <= 1:
            self.skipTest("No previous patch exists in the active release lane")
        previous = f"{major}.{minor}.{patch - 1}"

        for relative in (
            "SKILL.md",
            "README.md",
            ".claude-plugin/plugin.json",
            "gemini-extension.json",
            "scripts/lib/ui.py",
            "scripts/lib/bird_x.py",
            "scripts/lib/youtube_yt.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(previous, text, relative)
            self.assertNotIn(f"v{previous}", text, relative)


if __name__ == "__main__":
    unittest.main()
