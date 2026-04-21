import math
import json
import sqlite3
import tempfile
import unittest
from argparse import Namespace
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

    def test_load_portfolio_normalizes_entry_schema(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "AI coding tools markets to watch today",
                "enabled": True,
                "expected_pick_type": "watchlist",
            }
        ]), encoding="utf-8")

        entries = paper._load_portfolio(portfolio_path)

        self.assertEqual(entries[0]["expected_pick_types"], ["watchlist"])
        self.assertEqual(entries[0]["last24hours_args"], [])
        self.assertEqual(entries[0]["pick_policy"], "default")
        self.assertEqual(entries[0]["dedupe_policy"], "allow")
        self.assertEqual(entries[0]["dedupe_window_days"], 7)


class PaperExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_override = paper.store._db_override
        paper.store._db_override = Path(self.tmp.name) / "research.db"
        paper.store.init_db()

    def tearDown(self):
        paper.store._db_override = self.previous_override
        self.tmp.cleanup()

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
            "evidence_fusion_stats": {
                "source_health": {
                    "source_status": {
                        "reddit": {"status": "used"},
                        "x": {"status": "empty"},
                    }
                }
            },
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
                    "minutes_to_close": 43.0,
                    "closing_soon_reason": "closing_soon",
                    "live_game_context": "NBA 3rd Quarter; Lakers 78, Rockets 82",
                    "live_game_league": "nba",
                    "live_match_confidence": 0.85,
                    "live_match_reason": "direct_match",
                    "resolvability": "manual rule check required",
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
        notes = json.loads(picks[0]["notes_json"])
        self.assertEqual(notes["minutes_to_close"], 43.0)
        self.assertEqual(notes["closing_soon_reason"], "closing_soon")
        self.assertEqual(notes["live_game_league"], "nba")
        self.assertEqual(notes["live_match_confidence"], 0.85)
        self.assertEqual(notes["live_match_reason"], "direct_match")
        self.assertEqual(notes["resolvability"], "manual rule check required")
        evidence = json.loads(picks[0]["evidence_json"])
        self.assertEqual(evidence["source_health"]["source_status"]["x"]["status"], "empty")

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

    def test_filter_picks_by_policy(self):
        picks = [
            {"pick_type": "forecast", "title": "F"},
            {"pick_type": "watchlist", "title": "W"},
            {"pick_type": "bundle", "title": "B"},
        ]

        self.assertEqual([pick["title"] for pick in paper._filter_picks_by_policy(picks, "forecast_only")], ["F"])
        self.assertEqual([pick["title"] for pick in paper._filter_picks_by_policy(picks, "watchlist_only")], ["W"])
        self.assertEqual([pick["title"] for pick in paper._filter_picks_by_policy(picks, "bundle_only")], ["B"])
        self.assertEqual(len(paper._filter_picks_by_policy(picks, "default")), 3)

    def test_validate_expected_pick_types_warns_on_mismatch(self):
        warnings = paper._validate_expected_pick_types(
            {"topic": "NBA paper bundle today", "expected_pick_types": ["bundle"]},
            [{"pick_type": "watchlist"}],
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("expected pick types bundle", warnings[0])

    def test_cmd_daily_forwards_entry_args_and_pick_policy(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "Polymarket markets closing soon",
                "enabled": True,
                "last24hours_args": ["--closing-window-hours", "6"],
                "pick_policy": "watchlist_only",
                "expected_pick_types": ["watchlist"],
            }
        ]), encoding="utf-8")
        captured = []
        report = {
            "topic": "Polymarket markets closing soon",
            "query_type": "market_watchlist",
            "forecasts": [{"title": "Ignored forecast", "forecast_probability": 0.5, "anchor_source": "model_implied"}],
            "market_watchlist": [{"pick_type": "watchlist", "venue": "polymarket", "title": "Stored watchlist", "question": "Stored watchlist", "outcome_label": "Yes", "probability": 0.61, "url": "https://polymarket.com/event/stored-watchlist"}],
        }

        def fake_run(topic, quick, extra_args=None):
            captured.append((topic, quick, list(extra_args or [])))
            return report

        with mock.patch("scripts.paper._run_last24hours", side_effect=fake_run), \
             mock.patch("scripts.paper._write_daily_report", return_value=Path(self.tmp.name) / "paper-report.json"), \
             mock.patch("scripts.paper.resolve_open_picks", return_value=[]):
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=False))

        recent = paper.store.list_recent_paper_picks()
        self.assertEqual(captured, [("Polymarket markets closing soon", True, ["--closing-window-hours", "6"])])
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["pick_type"], "watchlist")

    def test_cmd_daily_skips_open_duplicates_under_entry_policy(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "Bitcoin above 100k this week",
                "enabled": True,
                "pick_policy": "forecast_only",
                "expected_pick_types": ["forecast"],
                "dedupe_policy": "skip_if_open_duplicate",
            }
        ]), encoding="utf-8")
        existing_run = paper.store.record_paper_run("existing")
        paper.store.add_paper_pick({
            "paper_run_id": existing_run,
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "pick_type": "forecast",
            "venue": "model_implied",
            "venue_market_key": "model_implied|Bitcoin above 100k this week|Bitcoin above 100k this week|2026-04-20",
            "title": "BTC above 100k",
            "model_probability": 0.42,
            "status": "unknown",
            "skill_version": "1.0.20",
        })
        report = {
            "topic": "Bitcoin above 100k this week",
            "query_type": "prediction",
            "generated_at": "2026-04-20T08:00:00",
            "forecasts": [
                {
                    "title": "Bitcoin above 100k this week",
                    "forecast_probability": 0.44,
                    "anchor_source": "model_implied",
                    "favorite_label": "Yes",
                    "confidence_level": "low",
                }
            ],
        }

        with mock.patch("scripts.paper._run_last24hours", return_value=report), \
             mock.patch("scripts.paper._write_daily_report", return_value=Path(self.tmp.name) / "paper-report.json"), \
             mock.patch("scripts.paper.resolve_open_picks", return_value=[]):
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=False))

        recent = paper.store.list_recent_paper_picks()
        self.assertEqual(len(recent), 1)


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

    def test_open_pick_diagnostics_tracks_bundles_without_manual_warning(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "unknown",
                "pick_type": "bundle",
                "venue": "paper_bundle",
                "model_probability": 0.42,
                "resolution_source": "",
                "skill_version": "1.0.18",
            },
            {
                "status": "unknown",
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "model_probability": 0.55,
                "resolution_source": "",
                "skill_version": "1.0.18",
            },
        ])

        self.assertEqual(diagnostics["paper_bundle_count"], 1)
        self.assertEqual(diagnostics["paper_only_bundle_count"], 1)
        self.assertEqual(diagnostics["manual_or_unknown_resolution_count"], 1)
        self.assertTrue(any("model-implied" in warning for warning in diagnostics["warnings"]))

    def test_open_pick_diagnostics_breaks_out_versions_domains_pick_types_and_duplicates(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "topic": "Bitcoin above 100k this week",
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "venue_market_key": "model_implied|btc-100k",
                "model_probability": 0.12,
                "resolution_source": "",
                "skill_version": "1.0.20",
                "created_at": "2026-04-20T08:00:00",
            },
            {
                "status": "open",
                "topic": "Bitcoin above 100k this week",
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "venue_market_key": "model_implied|btc-100k",
                "model_probability": 0.14,
                "resolution_source": "",
                "skill_version": "1.0.20",
                "created_at": "2026-04-18T08:00:00",
            },
            {
                "status": "unknown",
                "topic": "NBA paper bundle today",
                "pick_type": "bundle",
                "venue": "paper_bundle",
                "venue_market_key": "paper_bundle|nba|1",
                "model_probability": 0.44,
                "resolution_source": "",
                "skill_version": "",
                "created_at": "2026-04-10T08:00:00",
            },
        ])

        self.assertEqual(diagnostics["by_skill_version"]["1.0.20"], 2)
        self.assertEqual(diagnostics["by_skill_version"]["legacy_unversioned"], 1)
        self.assertEqual(diagnostics["by_pick_type"]["forecast"], 2)
        self.assertEqual(diagnostics["by_pick_type"]["bundle"], 1)
        self.assertEqual(diagnostics["by_domain"]["crypto"], 2)
        self.assertEqual(diagnostics["by_domain"]["nba"], 1)
        self.assertEqual(sum(diagnostics["by_age_bucket"].values()), 3)
        self.assertEqual(diagnostics["duplicate_market_key_count"], 1)
        self.assertEqual(diagnostics["duplicate_open_row_count"], 1)
        self.assertEqual(diagnostics["duplicate_clusters"]["model_implied|btc-100k"], 2)
        self.assertTrue(any("redundant duplicates" in warning for warning in diagnostics["warnings"]))

    def test_open_pick_diagnostics_tracks_legacy_noisy_rationale(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "topic": "Fed rate cut by June",
                "pick_type": "forecast",
                "venue": "model_implied",
                "model_probability": 0.52,
                "resolution_source": "",
                "skill_version": "1.0.18",
                "evidence_json": json.dumps({"why_line": "BREAKING: top traders say this VIP macro call keeps cashing."}),
            }
        ])

        self.assertEqual(diagnostics["legacy_noisy_rationale_count"], 1)
        self.assertTrue(any("legacy rationale text" in warning for warning in diagnostics["warnings"]))

    def test_calibration_summary_excludes_legacy_noisy_rationale_by_default(self):
        summary = paper.calibration_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.04,
                "log_loss": 0.22,
                "model_probability": 0.80,
                "venue": "kalshi",
                "anchor_source": "kalshi",
                "pick_type": "forecast",
                "market_type": "macro_binary",
                "confidence": "moderate",
                "topic": "Fed rate cut by June",
                "evidence_json": json.dumps({"why_line": "Official data release kept rate-cut pricing soft."}),
            },
            {
                "status": "resolved",
                "resolution_value": 0.0,
                "brier_score": 0.64,
                "log_loss": 1.60,
                "model_probability": 0.80,
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "pick_type": "forecast",
                "market_type": "model_implied",
                "confidence": "low",
                "topic": "Fed rate cut by June",
                "evidence_json": json.dumps({"why_line": "BREAKING: top traders say this VIP macro call keeps cashing."}),
            },
        ])

        self.assertEqual(summary["raw_resolved_count"], 2)
        self.assertEqual(summary["excluded_legacy_noisy_count"], 1)
        self.assertEqual(summary["count"], 1)


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
