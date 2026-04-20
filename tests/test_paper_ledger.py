import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import paper


class PaperStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_override = paper.store._db_override
        paper.store._db_override = Path(self.tmp.name) / "research.db"
        paper.store.init_db()

    def tearDown(self):
        paper.store._db_override = self.previous_override
        self.tmp.cleanup()

    def test_store_migration_creates_paper_tables(self):
        conn = sqlite3.connect(str(paper.store._db_override))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'paper_%'"
                )
            }
            run_columns = {row[1] for row in conn.execute("PRAGMA table_info(paper_runs)")}
            pick_columns = {row[1] for row in conn.execute("PRAGMA table_info(paper_picks)")}
        finally:
            conn.close()

        self.assertEqual(tables, {"paper_runs", "paper_picks"})
        self.assertIn("skill_version", run_columns)
        self.assertIn("skill_version", pick_columns)

    def test_repeated_paper_picks_are_preserved(self):
        run_id = paper.store.record_paper_run("paper_portfolio")
        payload = {
            "paper_run_id": run_id,
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "pick_type": "forecast",
            "venue": "kalshi",
            "venue_market_key": "KXBTC-100K",
            "title": "BTC above 100k",
            "model_probability": 0.42,
            "status": "open",
            "skill_version": "1.0.test",
        }

        first = paper.store.add_paper_pick(payload)
        second = paper.store.add_paper_pick(payload)

        self.assertNotEqual(first, second)
        self.assertEqual(len(paper.store.list_recent_paper_picks()), 2)
        self.assertEqual(paper.store.list_recent_paper_picks()[0]["skill_version"], "1.0.test")


class PaperExtractionTests(unittest.TestCase):
    def test_prediction_json_extracts_forecast_pick(self):
        report = {
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "generated_at": "2026-04-19T08:00:00",
            "kalshi": [
                {
                    "id": "K1",
                    "ticker": "KXBTC-100K",
                    "url": "https://kalshi.com/markets/KXBTC-100K",
                    "question": "Bitcoin above 100k this week?",
                    "implied_probability": 44,
                    "best_bid": 0.43,
                    "best_ask": 0.45,
                    "spread": 0.02,
                    "end_date": "2026-04-26",
                }
            ],
            "forecasts": [
                {
                    "title": "Bitcoin above 100k this week",
                    "forecast_probability": 0.46,
                    "kalshi_market_id": "K1",
                    "anchor_source": "kalshi",
                    "favorite_label": "Yes",
                    "confidence_level": "medium",
                }
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["venue"], "kalshi")
        self.assertEqual(picks[0]["venue_market_key"], "KXBTC-100K")
        self.assertEqual(picks[0]["model_probability"], 0.46)
        self.assertEqual(picks[0]["market_probability"], 0.44)
        self.assertEqual(picks[0]["skill_version"], paper._skill_version())

    def test_weather_forecast_pick_is_open_and_stores_target_date(self):
        report = {
            "topic": "NYC rain tomorrow",
            "query_type": "prediction",
            "generated_at": "2026-04-19T08:00:00",
            "forecasts": [
                {
                    "title": "NYC rain tomorrow",
                    "forecast_probability": 0.25,
                    "anchor_source": "weather_api",
                    "favorite_label": "Yes",
                    "confidence_level": "moderate-low",
                }
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["venue"], "weather_api")
        self.assertEqual(picks[0]["status"], "open")
        self.assertEqual(picks[0]["end_date"], "2026-04-20")
        self.assertTrue(picks[0]["venue_market_key"].endswith("|2026-04-20"))

    def test_watchlist_json_extracts_only_top_pick(self):
        report = {
            "topic": "AI coding tools markets to watch today",
            "query_type": "market_watchlist",
            "polymarket": [
                {
                    "id": "PM1",
                    "url": "https://polymarket.com/event/ai-coding-market",
                    "question": "AI coding market?",
                }
            ],
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "source_item_id": "PM1",
                    "title": "AI coding market",
                    "question": "AI coding market?",
                    "outcome_label": "Yes",
                    "probability": 0.61,
                    "url": "https://polymarket.com/event/ai-coding-market",
                },
                {
                    "venue": "kalshi",
                    "title": "Second pick",
                    "probability": 0.52,
                },
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["pick_type"], "watchlist")
        self.assertEqual(picks[0]["venue"], "polymarket")
        self.assertIn("ai-coding-market", picks[0]["venue_market_key"])

    def test_watchlist_json_prefers_balanced_pick_when_top_is_extreme_favorite(self):
        report = {
            "topic": "AI coding tools markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "Obvious favorite",
                    "question": "Favorite?",
                    "outcome_label": "Yes",
                    "probability": 0.94,
                    "url": "https://polymarket.com/event/favorite",
                },
                {
                    "venue": "polymarket",
                    "title": "Balanced market",
                    "question": "Balanced?",
                    "outcome_label": "Yes",
                    "probability": 0.58,
                    "url": "https://polymarket.com/event/balanced",
                },
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["title"], "Balanced market")
        self.assertAlmostEqual(picks[0]["model_probability"], 0.58)


class ResolverTests(unittest.TestCase):
    def test_kalshi_resolver_handles_open_and_settled_results(self):
        pick = {"outcome_label": "Yes"}

        self.assertEqual(
            paper._resolve_kalshi_payload(pick, {"market": {"status": "open"}}),
            ("open", None, "kalshi"),
        )
        self.assertEqual(
            paper._resolve_kalshi_payload(pick, {"market": {"status": "settled", "result": "yes"}}),
            ("resolved", 1.0, "kalshi"),
        )
        self.assertEqual(
            paper._resolve_kalshi_payload(pick, {"market": {"status": "settled", "result": "no"}}),
            ("resolved", 0.0, "kalshi"),
        )
        self.assertEqual(
            paper._resolve_kalshi_payload(pick, {"market": {"status": "settled"}}),
            ("unknown", None, "kalshi"),
        )

    def test_polymarket_resolver_handles_explicit_winner(self):
        pick = {"question": "Will BTC close above 100k?", "outcome_label": "Yes"}
        payload = {"events": [{"markets": [{"question": "Will BTC close above 100k?", "winner": "Yes"}]}]}

        self.assertEqual(paper._resolve_polymarket_payload(pick, payload), ("resolved", 1.0, "polymarket"))

    def test_polymarket_resolver_handles_top_level_event_list(self):
        pick = {"question": "Will BTC close above 100k?", "outcome_label": "Yes"}
        payload = [{"markets": [{"question": "Will BTC close above 100k?", "winner": "No"}]}]

        self.assertEqual(paper._resolve_polymarket_payload(pick, payload), ("resolved", 0.0, "polymarket"))

    def test_polymarket_resolver_handles_final_price_inference(self):
        pick = {"question": "Will BTC close above 100k?", "outcome_label": "Yes"}
        payload = {
            "events": [
                {
                    "closed": True,
                    "markets": [
                        {
                            "question": "Will BTC close above 100k?",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.01", "0.99"]',
                        }
                    ],
                }
            ]
        }

        self.assertEqual(paper._resolve_polymarket_payload(pick, payload), ("resolved", 0.0, "polymarket"))

    def test_polymarket_resolver_returns_unknown_for_no_match(self):
        pick = {"question": "Will BTC close above 100k?", "outcome_label": "Yes"}
        payload = {"events": [{"closed": True, "markets": [{"question": "Different market"}]}]}

        self.assertEqual(paper._resolve_polymarket_payload(pick, payload), ("unknown", None, "polymarket"))

    def test_nba_resolver_handles_final_winner(self):
        pick = {
            "topic": "tomorrows nba games",
            "title": "Raptors vs. Cavaliers",
            "outcome_label": "Cavaliers",
            "venue_market_key": "nba-tor-cle-2000-01-01|Raptors vs. Cavaliers|Cavaliers",
            "end_date": "2000-01-01",
        }
        payload = {
            "events": [{
                "name": "Toronto Raptors at Cleveland Cavaliers",
                "competitions": [{
                    "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
                    "competitors": [
                        {"team": {"displayName": "Toronto Raptors", "shortDisplayName": "Raptors"}},
                        {"winner": True, "team": {"displayName": "Cleveland Cavaliers", "shortDisplayName": "Cavaliers"}},
                    ],
                }],
            }]
        }

        with mock.patch("scripts.paper.http.get", return_value=payload):
            self.assertEqual(paper._resolve_nba_pick(pick), ("resolved", 1.0, "espn_nba"))

    def test_nba_resolver_handles_final_loser(self):
        pick = {
            "topic": "tomorrows nba games",
            "title": "Raptors vs. Cavaliers",
            "outcome_label": "Raptors",
            "venue_market_key": "nba-tor-cle-2000-01-01|Raptors vs. Cavaliers|Raptors",
            "end_date": "2000-01-01",
        }
        payload = {
            "events": [{
                "name": "Toronto Raptors at Cleveland Cavaliers",
                "competitions": [{
                    "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
                    "competitors": [
                        {"team": {"displayName": "Toronto Raptors", "shortDisplayName": "Raptors"}},
                        {"winner": True, "team": {"displayName": "Cleveland Cavaliers", "shortDisplayName": "Cavaliers"}},
                    ],
                }],
            }]
        }

        with mock.patch("scripts.paper.http.get", return_value=payload):
            self.assertEqual(paper._resolve_nba_pick(pick), ("resolved", 0.0, "espn_nba"))

    def test_nba_resolver_keeps_future_game_open(self):
        pick = {
            "topic": "tomorrows nba games",
            "title": "Raptors vs. Cavaliers",
            "outcome_label": "Cavaliers",
            "venue_market_key": "nba-tor-cle-2999-01-01|Raptors vs. Cavaliers|Cavaliers",
            "end_date": "2999-01-01",
        }

        with mock.patch("scripts.paper.http.get") as get:
            self.assertEqual(paper._resolve_nba_pick(pick), ("open", None, "espn_nba"))
        get.assert_not_called()

    def test_weather_resolver_handles_observed_rain(self):
        pick = {"topic": "NYC rain tomorrow", "venue": "weather_api", "end_date": "2000-01-01"}
        point = {"properties": {"observationStations": "https://api.weather.gov/gridpoints/OKX/stations"}}
        stations = {"features": [{"id": "https://api.weather.gov/stations/KNYC"}]}
        observations = {
            "features": [
                {"properties": {"precipitationLastHour": {"value": 0.8}, "textDescription": "Light Rain"}}
            ]
        }

        with mock.patch("scripts.paper.http.get", side_effect=[point, stations, observations]):
            self.assertEqual(paper._resolve_weather_pick(pick), ("resolved", 1.0, "nws_observations"))

    def test_weather_resolver_handles_observed_no_rain(self):
        pick = {"topic": "NYC rain tomorrow", "venue": "weather_api", "end_date": "2000-01-01"}
        point = {"properties": {"observationStations": "https://api.weather.gov/gridpoints/OKX/stations"}}
        stations = {"features": [{"id": "https://api.weather.gov/stations/KNYC"}]}
        observations = {
            "features": [
                {"properties": {"precipitationLastHour": {"value": 0}, "textDescription": "Fair"}}
            ]
        }

        with mock.patch("scripts.paper.http.get", side_effect=[point, stations, observations]):
            self.assertEqual(paper._resolve_weather_pick(pick), ("resolved", 0.0, "nws_observations"))

    def test_weather_resolver_keeps_future_date_open(self):
        pick = {"topic": "NYC rain tomorrow", "venue": "weather_api", "end_date": "2999-01-01"}

        with mock.patch("scripts.paper.http.get") as get:
            self.assertEqual(paper._resolve_weather_pick(pick), ("open", None, "nws_observations"))
        get.assert_not_called()


class CalibrationTests(unittest.TestCase):
    def test_brier_and_log_loss_calculations(self):
        self.assertAlmostEqual(paper.brier_score(0.7, 1.0), 0.09)
        self.assertAlmostEqual(paper.log_loss(0.7, 1.0), -math.log(0.7))

    def test_calibration_report_groups_by_expected_dimensions(self):
        picks = [
            {
                "status": "resolved",
                "topic": "Bitcoin above 100k this week",
                "venue": "kalshi",
                "anchor_source": "kalshi",
                "pick_type": "forecast",
                "market_type": "binary",
                "confidence": "medium",
                "model_probability": 0.75,
                "resolution_value": 1.0,
                "brier_score": 0.0625,
                "log_loss": 0.2877,
            },
            {
                "status": "resolved",
                "topic": "NYC rain tomorrow",
                "venue": "weather_api",
                "anchor_source": "weather_api",
                "pick_type": "forecast",
                "market_type": "weather",
                "confidence": "medium",
                "model_probability": 0.25,
                "resolution_value": 0.0,
                "brier_score": 0.0625,
                "log_loss": 0.2877,
            },
        ]

        summary = paper.calibration_summary(picks)

        self.assertEqual(summary["count"], 2)
        self.assertIn("venue:kalshi", summary["groups"])
        self.assertIn("domain:crypto", summary["groups"])
        self.assertIn("anchor_source:weather_api", summary["groups"])
        self.assertIn("confidence:medium", summary["groups"])
        self.assertIn("probability_bucket:65-80", summary["groups"])
        self.assertIn("probability_bucket:0-35", summary["groups"])
        self.assertAlmostEqual(summary["favorite_pick_rate"], 0.5)
        self.assertAlmostEqual(summary["longshot_pick_rate"], 0.5)
        self.assertAlmostEqual(summary["avg_edge_from_50"], 0.25)

    def test_suggest_refuses_small_samples(self):
        suggestions = paper.suggestions_from_summary({"count": 24, "groups": {}})

        self.assertEqual(len(suggestions), 1)
        self.assertIn("Need at least 25", suggestions[0])

    def test_suggest_uses_subgroup_thresholds(self):
        summary = {
            "count": 25,
            "avg_probability": 0.60,
            "observed_rate": 0.58,
            "groups": {
                "domain:crypto": {"count": 9, "avg_probability": 0.80, "observed_rate": 0.60},
                "venue:kalshi": {"count": 10, "avg_probability": 0.80, "observed_rate": 0.60},
            },
        }

        suggestions = paper.suggestions_from_summary(summary)

        self.assertEqual(len(suggestions), 1)
        self.assertIn("venue:kalshi", suggestions[0])
        self.assertNotIn("domain:crypto", suggestions[0])

    def test_suggest_flags_favorite_heavy_portfolios(self):
        summary = {
            "count": 25,
            "avg_probability": 0.72,
            "observed_rate": 0.72,
            "favorite_pick_rate": 0.76,
            "groups": {},
        }

        suggestions = paper.suggestions_from_summary(summary)

        self.assertEqual(len(suggestions), 1)
        self.assertIn("heavily concentrated in favorites", suggestions[0])

    def test_open_pick_diagnostics_flags_mix_and_legacy_samples(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "model_probability": 0.91,
                "venue": "polymarket",
                "resolution_source": "polymarket",
                "skill_version": "1.0.8",
            },
            {
                "status": "open",
                "model_probability": 0.88,
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "resolution_source": "",
                "skill_version": "",
            },
        ])

        self.assertEqual(diagnostics["mix"]["favorite"], 2)
        self.assertEqual(diagnostics["model_implied_count"], 1)
        self.assertEqual(diagnostics["legacy_unversioned_count"], 1)
        self.assertTrue(any("favorite-heavy" in warning for warning in diagnostics["warnings"]))
        self.assertTrue(any("legacy" in warning for warning in diagnostics["warnings"]))


class LaunchdTests(unittest.TestCase):
    def test_launchd_plist_contains_expected_daily_runner(self):
        plist = paper._launchd_plist("08:00")

        self.assertEqual(plist["Label"], "com.jask.last24hours.paper-daily")
        self.assertEqual(plist["WorkingDirectory"], str(paper.REPO_ROOT))
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 8, "Minute": 0})
        self.assertIn(str(paper.SCRIPT_DIR / "paper.py"), plist["ProgramArguments"])
        self.assertIn("daily", plist["ProgramArguments"])
        self.assertIn("--quick", plist["ProgramArguments"])
        self.assertTrue(plist["StandardOutPath"].endswith("paper-daily.out.log"))
        self.assertTrue(plist["StandardErrorPath"].endswith("paper-daily.err.log"))


class ResolveOpenPickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_override = paper.store._db_override
        paper.store._db_override = Path(self.tmp.name) / "research.db"
        paper.store.init_db()

    def tearDown(self):
        paper.store._db_override = self.previous_override
        self.tmp.cleanup()

    def test_resolve_open_pick_updates_scores(self):
        run_id = paper.store.record_paper_run("paper_portfolio")
        pick_id = paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "pick_type": "forecast",
            "venue": "kalshi",
            "venue_market_key": "KXBTC-100K",
            "title": "BTC above 100k",
            "question": "BTC above 100k?",
            "outcome_label": "Yes",
            "model_probability": 0.75,
            "status": "open",
        })

        with mock.patch("scripts.paper.http.request", return_value={"market": {"status": "settled", "result": "yes"}}):
            result = paper.resolve_open_picks()

        updated = paper.store.get_paper_pick(pick_id)
        self.assertEqual(result[0]["status"], "resolved")
        self.assertEqual(updated["resolution_value"], 1.0)
        self.assertAlmostEqual(updated["brier_score"], 0.0625)

    def test_resolve_network_error_leaves_pick_open_for_retry(self):
        run_id = paper.store.record_paper_run("paper_portfolio")
        pick_id = paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "pick_type": "forecast",
            "venue": "kalshi",
            "venue_market_key": "KXBTC-100K",
            "title": "BTC above 100k",
            "question": "BTC above 100k?",
            "outcome_label": "Yes",
            "model_probability": 0.75,
            "status": "open",
        })

        with mock.patch("scripts.paper.http.request", side_effect=RuntimeError("transient read failure")):
            result = paper.resolve_open_picks()

        updated = paper.store.get_paper_pick(pick_id)
        self.assertEqual(result[0]["status"], "open")
        self.assertEqual(updated["status"], "open")
        self.assertEqual(updated["resolution_source"], "retryable_error:RuntimeError")


if __name__ == "__main__":
    unittest.main()
