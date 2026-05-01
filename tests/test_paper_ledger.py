import io
import math
import json
import sqlite3
import subprocess
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

    def test_unresolved_pick_queue_includes_unknown_paper_bundles_only(self):
        run_id = paper.store.record_paper_run("paper_portfolio")
        paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "NBA paper bundle tomorrow",
            "query_type": "market_watchlist",
            "pick_type": "bundle",
            "venue": "paper_bundle",
            "venue_market_key": "paper_bundle|nba|1",
            "title": "Paper Bundle 1",
            "model_probability": 0.42,
            "status": "unknown",
            "skill_version": "1.0.test",
        })
        paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "NBA paper bundle next 2 days",
            "query_type": "market_watchlist",
            "pick_type": "bundle",
            "venue": "polymarket",
            "venue_market_key": "paper_bundle|nba|2",
            "title": "Paper Bundle 2",
            "model_probability": 0.38,
            "status": "unknown",
            "skill_version": "1.0.test",
        })
        paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "TenZ total kills tonight",
            "query_type": "prediction",
            "pick_type": "forecast",
            "venue": "model_implied",
            "venue_market_key": "model_implied|tenz",
            "title": "TenZ total kills tonight",
            "model_probability": 0.50,
            "status": "unknown",
            "skill_version": "1.0.test",
        })

        queued = paper.store.list_unresolved_paper_picks()
        keys = {row["venue_market_key"] for row in queued}

        self.assertIn("paper_bundle|nba|1", keys)
        self.assertIn("paper_bundle|nba|2", keys)
        self.assertNotIn("model_implied|tenz", keys)

    def test_bundle_dedupe_matches_equivalent_leg_sets_across_topics(self):
        legs = [
            {
                "source_item_id": "nba-lal-hou-2026-05-01",
                "title": "Lakers vs. Rockets",
                "outcome_label": "Rockets",
                "live_game_context": "NBA Fri, May 1st at 10:00 PM EDT; start 2026-05-02T02:00Z",
            },
            {
                "source_item_id": "nba-det-orl-2026-05-01",
                "title": "Pistons vs. Magic",
                "outcome_label": "Pistons",
                "live_game_context": "NBA Fri, May 1st at 7:00 PM EDT; start 2026-05-01T23:00Z",
            },
        ]
        run_id = paper.store.record_paper_run("paper_portfolio")
        paper.store.add_paper_pick({
            "paper_run_id": run_id,
            "topic": "NBA paper bundle next 2 days",
            "query_type": "market_watchlist",
            "pick_type": "bundle",
            "venue": "paper_bundle",
            "venue_market_key": "paper_bundle|nba|old-key",
            "title": "Paper Bundle 1",
            "market_type": "paper_bundle",
            "model_probability": 0.35,
            "status": "open",
            "notes_json": json.dumps({"domain": "nba", "legs": legs}),
            "skill_version": "1.0.test",
        })
        candidate = {
            "topic": "NBA paper bundle tomorrow",
            "pick_type": "bundle",
            "venue": "paper_bundle",
            "venue_market_key": "paper_bundle|nba|new-key",
            "notes_json": json.dumps({"domain": "nba", "legs": list(reversed(legs))}),
        }

        warnings = []
        debug = {}
        kept = paper._apply_dedupe_policy(
            {"topic": "NBA paper bundle tomorrow", "dedupe_policy": "skip_if_open_duplicate"},
            [candidate],
            warnings,
            debug,
        )

        self.assertEqual(kept, [])
        self.assertEqual(debug["skipped_duplicate_paper_rows"], 1)
        self.assertIn("skipped duplicate bundle", " ".join(warnings))

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

    def test_watchlist_json_prefers_calibration_useful_probability_over_extreme_favorite(self):
        report = {
            "topic": "Valorant markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "Valorant: Heavy Favorite vs Underdog",
                    "question": "Valorant: Heavy Favorite vs Underdog",
                    "outcome_label": "Heavy Favorite",
                    "probability": 0.91,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/valorant-heavy-favorite",
                },
                {
                    "venue": "polymarket",
                    "title": "Valorant: Balanced Team vs Other Team",
                    "question": "Valorant: Balanced Team vs Other Team",
                    "outcome_label": "Balanced Team",
                    "probability": 0.62,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/valorant-balanced",
                },
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertIn("Balanced Team", picks[0]["title"])
        self.assertEqual(picks[0]["model_probability"], 0.62)

    def test_watchlist_json_rejects_extreme_probability_only_non_closing_board(self):
        report = {
            "topic": "Valorant markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "Valorant: Heavy Favorite vs Underdog",
                    "question": "Valorant: Heavy Favorite vs Underdog",
                    "outcome_label": "Heavy Favorite",
                    "probability": 0.91,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/valorant-heavy-favorite",
                },
            ],
        }

        self.assertEqual(paper.extract_paper_picks(report), [])
        self.assertEqual(
            paper._dry_run_reason_class({"topic": "Valorant markets to watch today"}, report, []),
            "watchlist_extreme_probability_only",
        )

    def test_watchlist_json_rejects_extreme_longshot_only_non_closing_board(self):
        report = {
            "topic": "Valorant markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "Valorant: Longshot vs Favorite",
                    "question": "Valorant: Longshot vs Favorite",
                    "outcome_label": "Longshot",
                    "probability": 0.08,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/valorant-longshot",
                },
            ],
        }

        self.assertEqual(paper.extract_paper_picks(report), [])
        self.assertEqual(
            paper._dry_run_reason_class({"topic": "Valorant markets to watch today"}, report, []),
            "watchlist_extreme_probability_only",
        )

    def test_nba_watchlist_json_prefers_game_scope_over_near_tied_series_scope(self):
        report = {
            "topic": "NBA markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "source_item_id": "PM2",
                    "title": "NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                    "question": "NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                    "outcome_label": "Spurs",
                    "probability": 0.96,
                    "rank_score": 53,
                    "watchlist_scope": "series",
                    "url": "https://polymarket.com/event/nba-playoffs-who-will-win-series-spurs-vs-trail-blazers",
                },
                {
                    "venue": "polymarket",
                    "source_item_id": "PM1",
                    "title": "Trail Blazers vs. Spurs",
                    "question": "Trail Blazers vs. Spurs",
                    "outcome_label": "Spurs",
                    "probability": 0.84,
                    "rank_score": 56,
                    "watchlist_scope": "game",
                    "url": "https://polymarket.com/event/nba-por-sas-2026-04-21",
                },
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["title"], "Trail Blazers vs. Spurs")
        notes = json.loads(picks[0]["notes_json"])
        self.assertEqual(notes["watchlist_scope"], "game")

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

    def test_cs2_watchlist_pick_stores_esports_domain_and_subdomain(self):
        report = {
            "topic": "Counter-Strike 2 markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                    "question": "Counter-Strike: Astralis vs G2 (BO3) - BLAST Rivals Group A",
                    "outcome_label": "G2",
                    "probability": 0.53,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/cs2-astr-g2-2026-04-21",
                }
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        notes = json.loads(picks[0]["notes_json"])
        self.assertEqual(notes["domain"], "esports")
        self.assertEqual(notes["subdomain"], "cs2")

    def test_broad_esports_watchlist_pick_infers_market_subdomain(self):
        report = {
            "topic": "esports markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "LoL: NRG Esports vs Supernova (BO3) - NACL",
                    "question": "LoL: NRG Esports vs Supernova (BO3) - NACL",
                    "outcome_label": "NRG Esports",
                    "probability": 0.64,
                    "market_type": "game_outcome",
                    "url": "https://polymarket.com/event/lol-nrg-sn-2026-04-22",
                }
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        notes = json.loads(picks[0]["notes_json"])
        self.assertEqual(notes["domain"], "esports")
        self.assertEqual(notes["subdomain"], "lol")

    def test_esports_watchlist_pick_rejects_wrong_domain_market(self):
        report = {
            "topic": "donk total kills markets to watch today",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "polymarket",
                    "title": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                    "question": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                    "outcome_label": "Over 5.5",
                    "probability": 0.82,
                    "market_type": "player_prop",
                    "url": "https://polymarket.com/event/nba-playoffs-rockets-vs-lakers-total-games-ou-5pt5",
                }
            ],
        }

        self.assertEqual(paper.extract_paper_picks(report), [])

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
            "market_watchlist": [{
                "pick_type": "watchlist",
                "venue": "polymarket",
                "title": "Bitcoin Up or Down on April 22?",
                "question": "Bitcoin Up or Down on April 22?",
                "outcome_label": "Down",
                "probability": 0.61,
                "market_type": "crypto_daily",
                "minutes_to_close": 45.0,
                "closing_soon_reason": "closing_soon",
                "resolvability": "crypto reference-price market; verify Polymarket rules and live reference price",
                "url": "https://polymarket.com/event/stored-watchlist",
            }],
        }

        def fake_run(topic, quick, extra_args=None, timeout_seconds=None):
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

    def test_paper_watchlist_fast_args_uses_market_only_closing_soon_path(self):
        self.assertEqual(
            paper._paper_watchlist_fast_args("Polymarket markets closing soon", ["--closing-window-hours", "6"]),
            ["--closing-window-hours", "6", "--paper-fast-watchlist", "--search", "polymarket"],
        )
        self.assertEqual(
            paper._paper_watchlist_fast_args("Kalshi markets closing soon", []),
            ["--paper-fast-watchlist", "--search", "kalshi"],
        )
        self.assertEqual(
            paper._paper_watchlist_fast_args("AI coding tools markets to watch today", []),
            [],
        )

    def test_cmd_daily_dry_run_reports_no_compatible_and_degraded_statuses(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "Counter-Strike 2 matches today", "enabled": True},
            {"topic": "Fed rate cut by June", "enabled": True},
        ]), encoding="utf-8")
        reports = {
            "Counter-Strike 2 matches today": {
                "topic": "Counter-Strike 2 matches today",
                "query_type": "prediction",
                "forecasts": [],
                "market_watchlist": [],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
            "Fed rate cut by June": {
                "topic": "Fed rate cut by June",
                "query_type": "prediction",
                "forecasts": [{"title": "Fed rate cut by June", "model_implied": True}],
                "market_watchlist": [],
                "evidence_fusion_stats": {"source_health": {"source_status": {"kalshi": {"status": "degraded"}}}},
            },
        }

        with mock.patch("scripts.paper._run_last24hours", side_effect=lambda topic, quick, extra_args=None, timeout_seconds=None: reports[topic]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        by_topic = {entry["topic"]: entry for entry in payload["results"]}
        self.assertEqual(by_topic["Counter-Strike 2 matches today"]["status"], "no_compatible_pick")
        self.assertEqual(by_topic["Counter-Strike 2 matches today"]["reason_class"], "no_compatible_market")
        self.assertEqual(by_topic["Fed rate cut by June"]["status"], "degraded_run")
        self.assertEqual(by_topic["Fed rate cut by June"]["reason_class"], "degraded_evidence_only")

    def test_cmd_daily_dry_run_reports_closing_soon_reason_classes(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "Polymarket markets closing soon", "enabled": True},
            {"topic": "crypto markets closing soon tonight", "enabled": True},
        ]), encoding="utf-8")
        reports = {
            "Polymarket markets closing soon": {
                "topic": "Polymarket markets closing soon",
                "query_type": "market_watchlist",
                "forecasts": [],
                "market_watchlist": [],
                "planning_notes": [
                    "closing_soon",
                    "closing-pm-candidates:0",
                    "closing-pm-skipped-settled:2",
                    "closing-ka-candidates:0",
                    "closing-ka-skipped-settled:0",
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"polymarket": {"status": "used"}}}},
            },
            "crypto markets closing soon tonight": {
                "topic": "crypto markets closing soon tonight",
                "query_type": "market_watchlist",
                "forecasts": [],
                "market_watchlist": [],
                "polymarket": [
                    {
                        "title": "Highest temperature in Shanghai on April 22?",
                        "question": "Will the highest temperature in Shanghai be 18C on April 22?",
                        "url": "https://polymarket.com/event/shanghai-temp",
                        "market_type": "weather_binary",
                        "minutes_to_close": 45.0,
                        "closing_soon_reason": "closing_soon",
                        "resolvability": "weather market; verify the official station/source before treating it as resolved",
                    }
                ],
                "planning_notes": ["closing_soon", "closing-pm-candidates:1", "closing-ka-candidates:0"],
                "evidence_fusion_stats": {"source_health": {"source_status": {"polymarket": {"status": "used"}}}},
            },
        }

        with mock.patch("scripts.paper._run_last24hours", side_effect=lambda topic, quick, extra_args=None, timeout_seconds=None: reports[topic]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        by_topic = {entry["topic"]: entry for entry in payload["results"]}
        self.assertEqual(by_topic["Polymarket markets closing soon"]["status"], "no_compatible_pick")
        self.assertEqual(by_topic["Polymarket markets closing soon"]["reason_class"], "all_candidates_effectively_settled")
        self.assertEqual(by_topic["crypto markets closing soon tonight"]["reason_class"], "domain_mismatch")

    def test_cmd_daily_dry_run_reports_bundle_specific_reason_classes(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "NBA paper bundle next 2 days",
                "enabled": True,
                "pick_policy": "bundle_only",
                "expected_pick_types": ["bundle"],
            }
        ]), encoding="utf-8")
        report = {
            "topic": "NBA paper bundle next 2 days",
            "query_type": "market_watchlist",
            "forecasts": [],
            "market_watchlist": [],
            "paper_bundles": [],
            "paper_bundle_reason": "no future NBA games found in the requested bundle window.",
            "evidence_fusion_stats": {"source_health": {"source_status": {"polymarket": {"status": "used"}}}},
        }

        with mock.patch("scripts.paper._run_last24hours", return_value=report), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["results"][0]["status"], "no_compatible_pick")
        self.assertEqual(payload["results"][0]["reason_class"], "no_future_games_in_window")

    def test_extract_paper_picks_rejects_non_crypto_closing_soon_watchlist_row(self):
        report = {
            "topic": "crypto markets closing soon tonight",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "Polymarket",
                    "title": "Highest temperature in Shanghai on April 22?",
                    "question": "Will the highest temperature in Shanghai be 18C on April 22?",
                    "outcome_label": "Yes",
                    "probability": 0.58,
                    "market_type": "weather_binary",
                    "url": "https://polymarket.com/event/shanghai-temp",
                    "minutes_to_close": 45.0,
                    "closing_soon_reason": "closing_soon",
                    "resolvability": "weather market; verify the official station/source before treating it as resolved",
                }
            ],
            "polymarket": [],
            "kalshi": [],
        }

        self.assertEqual(paper.extract_paper_picks(report), [])

    def test_kalshi_live_board_watchlist_is_not_treated_as_closing_soon(self):
        report = {
            "topic": "Kalshi live markets",
            "query_type": "market_watchlist",
            "market_watchlist": [
                {
                    "venue": "Kalshi",
                    "title": "CPI in May",
                    "question": "Will CPI rise more than 0.5% in May 2026?",
                    "outcome_label": "Yes",
                    "probability": 0.35,
                    "implied_probability": 0.35,
                    "market_type": "macro_binary",
                    "url": "https://api.elections.kalshi.com/trade-api/v2/markets/KXCPI-26MAY-T0.5",
                    "source_item_id": "KA1",
                    "end_date": "2026-06-10",
                }
            ],
            "polymarket": [],
            "kalshi": [
                {
                    "id": "KA1",
                    "ticker": "KXCPI-26MAY-T0.5",
                    "title": "CPI in May",
                    "question": "Will CPI rise more than 0.5% in May 2026?",
                    "url": "https://api.elections.kalshi.com/trade-api/v2/markets/KXCPI-26MAY-T0.5",
                    "market_type": "macro_binary",
                    "implied_probability": 0.35,
                    "best_bid": 0.34,
                    "best_ask": 0.35,
                    "spread": 0.01,
                    "end_date": "2026-06-10",
                }
            ],
        }

        picks = paper.extract_paper_picks(report)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["topic"], "Kalshi live markets")
        self.assertEqual(picks[0]["venue"], "kalshi")
        self.assertEqual(picks[0]["market_type"], "macro_binary")
        self.assertEqual(picks[0]["status"], "open")

    def test_kalshi_live_board_keeps_normal_watchlist_forwarding_args(self):
        self.assertEqual(
            paper._paper_watchlist_fast_args("Kalshi live markets", ["--search=kalshi"]),
            ["--search=kalshi"],
        )
        self.assertIn(
            "--paper-fast-watchlist",
            paper._paper_watchlist_fast_args("Kalshi markets closing soon", ["--search=kalshi"]),
        )

    def test_closing_soon_health_summary_groups_watchlist_rows(self):
        picks = [
            {
                "topic": "Polymarket markets closing soon",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "market_type": "crypto_daily",
                "status": "open",
                "anchor_source": "polymarket",
            },
            {
                "topic": "Kalshi markets closing soon",
                "pick_type": "watchlist",
                "venue": "kalshi",
                "market_type": "threshold",
                "status": "resolved",
                "anchor_source": "kalshi",
            },
        ]

        summary = paper.closing_soon_health_summary(picks)

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["open_count"], 1)
        self.assertEqual(summary["resolved_count"], 1)
        self.assertEqual(summary["by_venue"]["kalshi"], 1)
        self.assertEqual(summary["by_market_type"]["crypto_daily"], 1)
        self.assertEqual(summary["open_anchor_mix"]["anchored"], 1)

    def test_closing_soon_health_summary_excludes_kalshi_live_board(self):
        picks = [
            {
                "topic": "Kalshi live markets",
                "pick_type": "watchlist",
                "venue": "kalshi",
                "market_type": "macro_binary",
                "status": "open",
                "anchor_source": "kalshi",
            },
            {
                "topic": "Kalshi markets closing soon",
                "pick_type": "watchlist",
                "venue": "kalshi",
                "market_type": "threshold",
                "status": "open",
                "anchor_source": "kalshi",
            },
        ]

        summary = paper.closing_soon_health_summary(picks)

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["by_market_type"], {"threshold": 1})

    def test_kalshi_live_board_summary_tracks_live_board_separately(self):
        picks = [
            {
                "id": 10,
                "topic": "Kalshi live markets",
                "pick_type": "watchlist",
                "venue": "kalshi",
                "market_type": "macro_binary",
                "status": "open",
                "title": "CPI in May",
                "model_probability": 0.35,
                "skill_version": "1.0.86",
            },
            {
                "id": 11,
                "topic": "Kalshi markets closing soon",
                "pick_type": "watchlist",
                "venue": "kalshi",
                "market_type": "threshold",
                "status": "open",
                "title": "BTC above target",
            },
        ]

        live = paper.kalshi_live_board_summary(picks)
        closing = paper.closing_soon_health_summary(picks)

        self.assertEqual(live["count"], 1)
        self.assertEqual(live["by_market_type"], {"macro_binary": 1})
        self.assertEqual(live["rows"][0]["title"], "CPI in May")
        self.assertEqual(closing["count"], 1)
        self.assertEqual(closing["by_market_type"], {"threshold": 1})

    def test_recent_resolution_summary_groups_freshly_resolved_rows(self):
        picks = [
            {
                "id": 116,
                "topic": "Valorant matches today",
                "title": "Valorant: BBL Esports vs Team Vitality",
                "pick_type": "forecast",
                "venue": "polymarket",
                "market_type": "game_outcome",
                "resolution_source": "polymarket",
                "resolution_value": 1.0,
                "model_probability": 0.58,
                "brier_score": 0.1764,
                "status": "resolved",
                "resolved_at": "2026-04-24 12:00:00",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant"}),
            },
            {
                "id": 117,
                "topic": "NYC rain tomorrow",
                "title": "NYC rain tomorrow",
                "pick_type": "forecast",
                "venue": "weather_api",
                "market_type": "weather",
                "resolution_source": "nws_observations",
                "resolution_value": 0.0,
                "model_probability": 0.25,
                "brier_score": 0.0625,
                "status": "resolved",
                "resolved_at": "2026-04-20 12:00:00",
            },
            {
                "id": 118,
                "topic": "Counter-Strike 2 matches today",
                "status": "open",
                "resolution_value": None,
            },
        ]

        summary = paper.recent_resolution_summary(
            picks,
            hours=48,
            now=paper.datetime(2026, 4, 24, 13, 0, 0),
        )

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["by_domain"]["esports"], 1)
        self.assertEqual(summary["by_pick_type"]["forecast"], 1)
        self.assertEqual(summary["by_market_type"]["game_outcome"], 1)
        self.assertEqual(summary["by_resolution_source"]["polymarket"], 1)
        self.assertEqual(summary["rows"][0]["id"], 116)
        self.assertEqual(summary["rows"][0]["subdomain"], "valorant")

    def test_resolution_learning_summary_flags_high_confidence_misses_and_groups(self):
        picks = [
            {
                "id": 201,
                "topic": "Valorant markets to watch today",
                "title": "Valorant: BBL Esports vs Team Vitality",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "market_type": "game_outcome",
                "model_probability": 0.91,
                "resolution_value": 0.0,
                "brier_score": 0.8281,
                "status": "resolved",
                "resolved_at": "2026-04-24 12:00:00",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant"}),
            },
            {
                "id": 202,
                "topic": "Valorant matches today",
                "title": "Valorant: Gentle Mates vs Team Heretics",
                "pick_type": "forecast",
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "market_type": "game_outcome",
                "model_probability": 0.72,
                "resolution_value": 1.0,
                "brier_score": 0.0784,
                "status": "resolved",
                "resolved_at": "2026-04-24 13:00:00",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant"}),
            },
            {
                "id": 203,
                "topic": "Counter-Strike 2 matches today",
                "title": "Counter-Strike: BIG vs Heroic",
                "pick_type": "forecast",
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "market_type": "game_outcome",
                "model_probability": 0.28,
                "resolution_value": 1.0,
                "brier_score": 0.5184,
                "status": "resolved",
                "resolved_at": "2026-04-24 14:00:00",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
            },
        ]

        summary = paper.resolution_learning_summary(picks, min_group_count=2)

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["worst_rows"][0]["id"], 201)
        self.assertEqual(summary["high_confidence_misses"][0]["id"], 201)
        self.assertEqual(summary["underdog_hits"][0]["id"], 203)
        self.assertTrue(any(alert["axis"] == "domain" and alert["value"] == "esports" for alert in summary["group_alerts"]))
        self.assertTrue(any("high-confidence miss" in item for item in summary["action_items"]))

    def test_probability_bucket_health_summary_flags_65_80_calibration_gap(self):
        picks = [
            {
                "id": idx,
                "topic": "Calibration row",
                "title": f"Calibration row {idx}",
                "pick_type": "forecast",
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "market_type": "game_outcome",
                "model_probability": probability,
                "resolution_value": outcome,
                "brier_score": (probability - outcome) ** 2,
                "status": "resolved",
            }
            for idx, probability, outcome in (
                (301, 0.72, 0.0),
                (302, 0.74, 0.0),
                (303, 0.68, 1.0),
                (304, 0.77, 0.0),
                (305, 0.66, 0.0),
            )
        ]

        summary = paper.probability_bucket_health_summary(picks, bucket="65-80", min_count=3)

        self.assertEqual(summary["bucket"], "65-80")
        self.assertEqual(summary["count"], 5)
        self.assertTrue(summary["flagged"])
        self.assertEqual(summary["direction"], "overconfident")
        self.assertIn("probability_bucket:65-80", summary["operator_note"])
        self.assertEqual(summary["worst_rows"][0]["id"], 304)

    def test_cmd_daily_dry_run_reports_wrong_subdomain_reason_class(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "TenZ total kills tonight", "enabled": True},
        ]), encoding="utf-8")
        report = {
            "topic": "TenZ total kills tonight",
            "query_type": "prediction",
            "forecasts": [],
            "market_watchlist": [],
            "polymarket": [
                {
                    "title": "Counter-Strike 2: donk total kills > 18.5 - Map 1",
                    "question": "Will donk get more than 18.5 kills?",
                    "url": "https://polymarket.com/event/cs2-donk-kills",
                }
            ],
            "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
        }

        with mock.patch("scripts.paper._run_last24hours", return_value=report), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        entry = payload["results"][0]
        self.assertEqual(entry["status"], "no_compatible_pick")
        self.assertEqual(entry["reason_class"], "wrong_subdomain")
        self.assertIn("wrong_subdomain", " ".join(entry["warnings"]))

    def test_cmd_daily_dry_run_adds_esports_watchlist_failure_counters(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "Counter-Strike 2 markets to watch today", "enabled": True, "pick_policy": "watchlist_only"},
        ]), encoding="utf-8")
        report = {
            "topic": "Counter-Strike 2 markets to watch today",
            "query_type": "market_watchlist",
            "generated_at": "2026-04-22T18:00:00+00:00",
            "forecasts": [],
            "market_watchlist": [],
            "polymarket": [
                {
                    "title": "Counter-Strike: Vitality vs G2 (BO3)",
                    "question": "Counter-Strike: Vitality vs G2 (BO3)",
                    "url": "https://polymarket.com/event/cs2-vit-g2-2026-04-23",
                    "market_type": "game_outcome",
                    "end_date": "2026-04-23",
                    "probability": 0.56,
                }
            ],
            "evidence_fusion_stats": {"source_health": {"source_status": {"web": {"status": "empty"}}}},
        }

        with mock.patch("scripts.paper._run_last24hours", return_value=report), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        entry = payload["results"][0]
        self.assertEqual(entry["status"], "no_compatible_pick")
        self.assertEqual(entry["debug_counters"]["esports_watchlist_filtered_later_date_rows"], 1)
        self.assertEqual(entry["debug_counters"]["esports_watchlist_no_same_day_direct_rows"], 1)
        self.assertIn("later-date", entry["diagnostic_summary"])
        self.assertIn("no same-day direct", entry["diagnostic_summary"])

    def test_cmd_daily_dry_run_reports_named_prop_reason_classes(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "TenZ total kills tonight", "enabled": True},
            {"topic": "Faker total kills tonight", "enabled": True},
            {"topic": "Faker solo kills tonight", "enabled": True},
        ]), encoding="utf-8")
        reports = {
            "TenZ total kills tonight": {
                "topic": "TenZ total kills tonight",
                "query_type": "prediction",
                "generated_at": "2026-04-22T18:00:00+00:00",
                "forecasts": [{"title": "TenZ total kills tonight", "forecast_probability": 0.52, "anchor_source": "model_implied"}],
                "market_watchlist": [],
                "polymarket": [
                    {
                        "title": "yay total kills > 17.5 - Map 1",
                        "question": "Will yay get more than 17.5 kills tonight?",
                        "url": "https://polymarket.com/event/val-yay-kills-2026-04-22",
                        "market_type": "esports_prop",
                        "end_date": "2026-04-22",
                    }
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
            "Faker total kills tonight": {
                "topic": "Faker total kills tonight",
                "query_type": "prediction",
                "generated_at": "2026-04-22T18:00:00+00:00",
                "forecasts": [{"title": "Faker total kills tonight", "forecast_probability": 0.51, "anchor_source": "model_implied"}],
                "market_watchlist": [],
                "polymarket": [
                    {
                        "title": "Faker kill line - Game 1",
                        "question": "Will Faker record more than 4.5 kills on 2026-04-24?",
                        "url": "https://polymarket.com/event/lol-faker-kill-line-2026-04-24",
                        "market_type": "esports_prop",
                        "end_date": "2026-04-24",
                    }
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
            "Faker solo kills tonight": {
                "topic": "Faker solo kills tonight",
                "query_type": "prediction",
                "generated_at": "2026-04-22T18:00:00+00:00",
                "forecasts": [{"title": "Faker solo kills tonight", "forecast_probability": 0.5, "anchor_source": "model_implied"}],
                "market_watchlist": [],
                "polymarket": [
                    {
                        "title": "Faker kill line - Game 1",
                        "question": "Will Faker record more than 4.5 kills tonight?",
                        "url": "https://polymarket.com/event/lol-faker-kill-line-2026-04-22",
                        "market_type": "esports_prop",
                        "end_date": "2026-04-22",
                    }
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
        }

        with mock.patch("scripts.paper._run_last24hours", side_effect=lambda topic, quick, extra_args=None, timeout_seconds=None: reports[topic]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        by_topic = {entry["topic"]: entry for entry in payload["results"]}
        self.assertEqual(by_topic["TenZ total kills tonight"]["degraded_reason_class"], "no_matching_player_market")
        self.assertEqual(by_topic["TenZ total kills tonight"]["status"], "no_compatible_pick")
        self.assertEqual(by_topic["Faker total kills tonight"]["degraded_reason_class"], "no_same_day_prop_market")
        self.assertEqual(by_topic["Faker solo kills tonight"]["degraded_reason_class"], "wrong_stat_family")

    def test_esports_prop_model_implied_rows_are_admission_filtered(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "TenZ total kills tonight",
                "enabled": True,
                "expected_pick_types": ["forecast"],
                "pick_policy": "forecast_only",
                "dedupe_policy": "skip_if_open_duplicate",
            },
        ]), encoding="utf-8")
        report = {
            "topic": "TenZ total kills tonight",
            "query_type": "prediction",
            "generated_at": "2026-04-22T18:00:00+00:00",
            "forecasts": [{"title": "TenZ total kills tonight", "forecast_probability": 0.52, "anchor_source": "model_implied"}],
            "market_watchlist": [],
            "polymarket": [],
            "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
        }

        with mock.patch("scripts.paper._run_last24hours", return_value=report), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        entry = payload["results"][0]
        self.assertEqual(entry["status"], "no_compatible_pick")
        self.assertEqual(entry["post_admission_pick_count"], 0)
        self.assertEqual(entry["reason_class"], "degraded_model_implied_only")
        self.assertIn("skipped model-implied eSports prop", " ".join(entry["warnings"]))

    def test_cmd_daily_dry_run_reports_wrong_domain_and_market_type_reason_classes(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "donk total kills markets to watch today", "enabled": True},
            {"topic": "TenZ total kills tonight", "enabled": True},
        ]), encoding="utf-8")
        reports = {
            "donk total kills markets to watch today": {
                "topic": "donk total kills markets to watch today",
                "query_type": "market_watchlist",
                "forecasts": [],
                "market_watchlist": [
                    {
                        "venue": "polymarket",
                        "title": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                        "question": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                        "outcome_label": "Over 5.5",
                        "probability": 0.82,
                        "market_type": "player_prop",
                        "url": "https://polymarket.com/event/nba-playoffs-rockets-vs-lakers-total-games-ou-5pt5",
                    }
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
            "TenZ total kills tonight": {
                "topic": "TenZ total kills tonight",
                "query_type": "market_watchlist",
                "forecasts": [],
                "market_watchlist": [
                    {
                        "venue": "polymarket",
                        "title": "Valorant: Sentinels vs 100 Thieves winner",
                        "question": "Valorant: Sentinels vs 100 Thieves winner",
                        "outcome_label": "Sentinels",
                        "probability": 0.61,
                        "market_type": "game_outcome",
                        "url": "https://polymarket.com/event/valorant-sen-100t-2026-04-22",
                    }
                ],
                "evidence_fusion_stats": {"source_health": {"source_status": {"x": {"status": "used"}}}},
            },
        }

        with mock.patch("scripts.paper._run_last24hours", side_effect=lambda topic, quick, extra_args=None, timeout_seconds=None: reports[topic]), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        by_topic = {entry["topic"]: entry for entry in payload["results"]}
        self.assertEqual(by_topic["donk total kills markets to watch today"]["reason_class"], "wrong_domain_market")
        self.assertEqual(by_topic["TenZ total kills tonight"]["reason_class"], "wrong_market_type")

    def test_cmd_daily_dry_run_reports_timeout_as_error_status(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {"topic": "Counter-Strike 2 matches today", "enabled": True},
        ]), encoding="utf-8")

        with mock.patch(
            "scripts.paper._run_last24hours",
            side_effect=subprocess.TimeoutExpired(cmd=["python3"], timeout=paper.DRY_RUN_TOPIC_TIMEOUT_SECONDS),
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        entry = payload["results"][0]
        self.assertEqual(entry["status"], "error")
        self.assertIn("timed out", " ".join(entry["warnings"]).lower())

    def test_cmd_daily_dry_run_classifies_kalshi_closing_timeout(self):
        portfolio_path = Path(self.tmp.name) / "portfolio.json"
        portfolio_path.write_text(json.dumps([
            {
                "topic": "Kalshi markets closing soon",
                "enabled": True,
                "last24hours_args": ["--closing-window-hours", "6"],
            },
        ]), encoding="utf-8")

        with mock.patch(
            "scripts.paper._run_last24hours",
            side_effect=subprocess.TimeoutExpired(cmd=["python3"], timeout=paper.DRY_RUN_TOPIC_TIMEOUT_SECONDS),
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            paper.cmd_daily(Namespace(portfolio=str(portfolio_path), quick=True, dry_run=True))

        payload = json.loads(stdout.getvalue())
        entry = payload["results"][0]
        self.assertEqual(entry["status"], "degraded_run")
        self.assertEqual(entry["reason_class"], "kalshi_closing_soon_timeout")
        self.assertIn("bounded degraded scan", " ".join(entry["warnings"]).lower())

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

    def test_crypto_resolver_above_threshold_resolves_yes(self):
        pick = {"topic": "Bitcoin above 100k this week", "end_date": "2000-01-01"}
        payload = {"bitcoin": {"usd": 105000.0}}
        with mock.patch("scripts.paper.http.get", return_value=payload):
            self.assertEqual(paper._resolve_crypto_pick(pick), ("resolved", 1.0, "coingecko"))

    def test_crypto_resolver_below_threshold_resolves_no(self):
        pick = {"topic": "Bitcoin above 100k this week", "end_date": "2000-01-01"}
        payload = {"bitcoin": {"usd": 92000.0}}
        with mock.patch("scripts.paper.http.get", return_value=payload):
            self.assertEqual(paper._resolve_crypto_pick(pick), ("resolved", 0.0, "coingecko"))

    def test_crypto_resolver_below_direction_resolves_correctly(self):
        pick = {"topic": "Ethereum below 3k this week", "end_date": "2000-01-01"}
        payload = {"ethereum": {"usd": 2500.0}}
        with mock.patch("scripts.paper.http.get", return_value=payload):
            self.assertEqual(paper._resolve_crypto_pick(pick), ("resolved", 1.0, "coingecko"))

    def test_crypto_resolver_future_date_stays_open(self):
        pick = {"topic": "Bitcoin above 100k this week", "end_date": "2999-01-01"}
        with mock.patch("scripts.paper.http.get") as get:
            self.assertEqual(paper._resolve_crypto_pick(pick), ("open", None, "coingecko"))
        get.assert_not_called()

    def test_crypto_resolver_unparseable_threshold_is_manual(self):
        pick = {"topic": "Bitcoin maybe something", "end_date": "2000-01-01"}
        with mock.patch("scripts.paper.http.get") as get:
            status, value, source = paper._resolve_crypto_pick(pick)
        self.assertEqual(status, "unknown")
        self.assertIsNone(value)
        self.assertEqual(source, "manual_required")
        get.assert_not_called()

    def test_crypto_resolver_parses_k_suffix_and_direction(self):
        parsed = paper._parse_crypto_threshold("Bitcoin above 100k this week")
        self.assertEqual(parsed, ("bitcoin", "above", 100_000.0))
        parsed = paper._parse_crypto_threshold("ETH under 3,500 by end of month")
        self.assertEqual(parsed, ("ethereum", "below", 3_500.0))


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

    def test_open_pick_diagnostics_model_implied_groups_use_all_rows(self):
        rows = []
        for idx in range(13):
            topic = "TenZ total kills tonight" if idx < 8 else "Bitcoin above 100k this week"
            rows.append({
                "id": idx + 1,
                "status": "unknown",
                "topic": topic,
                "title": topic,
                "question": topic,
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "venue_market_key": f"model_implied|{idx}",
                "market_type": "model_implied",
                "model_probability": 0.50,
                "resolution_source": "",
                "skill_version": "1.0.83",
                "notes_json": json.dumps({
                    "domain": "esports" if idx < 8 else "crypto",
                    "subdomain": "valorant" if idx < 8 else "",
                    "degraded_reason_class": "degraded_model_implied_only",
                }),
            })

        diagnostics = paper.open_pick_diagnostics(rows)
        model_implied = diagnostics["model_implied_open_slice"]

        self.assertEqual(model_implied["count"], 13)
        self.assertEqual(sum(model_implied["by_domain"].values()), 13)
        self.assertEqual(model_implied["by_domain"]["esports"], 8)
        self.assertEqual(model_implied["by_domain"]["crypto"], 5)
        self.assertEqual(model_implied["by_subdomain"]["valorant"], 8)
        self.assertEqual(len(model_implied["rows"]), 10)
        esports_slice = diagnostics["open_model_implied_esports_slice"]
        self.assertEqual(esports_slice["count"], 8)
        self.assertEqual(esports_slice["by_topic"]["TenZ total kills tonight"], 8)
        self.assertEqual(esports_slice["by_subdomain"]["valorant"], 8)
        self.assertEqual(esports_slice["by_skill_version"]["1.0.83"], 8)
        self.assertEqual(esports_slice["by_degraded_reason_class"]["degraded_model_implied_only"], 8)

    def test_open_pick_diagnostics_bundle_groups_use_all_rows(self):
        rows = []
        for idx in range(12):
            legs = [
                {
                    "title": "Celtics vs. 76ers",
                    "outcome_label": "Celtics",
                    "live_game_context": "NBA Thu, April 30th at 8:00 PM EDT; start 2026-05-01T00:00Z",
                },
                {
                    "title": "Knicks vs. Hawks",
                    "outcome_label": "Knicks",
                    "live_game_context": "NBA Thu, April 30th at 7:00 PM EDT; start 2026-04-30T23:00Z",
                },
            ]
            if idx >= 10:
                legs.append({
                    "title": "Lakers vs. Rockets",
                    "outcome_label": "Lakers",
                    "live_game_context": "NBA Thu, April 30th at 10:00 PM EDT; start 2026-05-01T02:00Z",
                })
            rows.append({
                "id": idx + 1,
                "status": "unknown",
                "topic": "NBA paper bundle tomorrow" if idx % 2 else "NBA paper bundle next 2 days",
                "title": f"Paper Bundle {idx + 1}",
                "pick_type": "bundle",
                "venue": "paper_bundle",
                "venue_market_key": f"paper_bundle|nba|{idx}",
                "model_probability": 0.40,
                "resolution_source": "",
                "skill_version": "1.0.83",
                "created_at": "2026-04-20 08:00:00",
                "notes_json": json.dumps({"domain": "nba", "legs": legs}),
            })

        diagnostics = paper.open_pick_diagnostics(rows)
        bundles = diagnostics["paper_bundle_open_slice"]

        self.assertEqual(bundles["count"], 12)
        self.assertEqual(sum(bundles["by_age_bucket"].values()), 12)
        self.assertEqual(bundles["by_leg_count"]["2"], 10)
        self.assertEqual(bundles["by_leg_count"]["3"], 2)
        self.assertEqual(len(bundles["rows"]), 10)
        duplicate_slice = diagnostics["paper_bundle_duplicate_slice"]
        self.assertEqual(duplicate_slice["duplicate_group_count"], 2)
        self.assertEqual(duplicate_slice["duplicate_open_row_count"], 10)
        self.assertTrue(all(group["count"] > 1 for group in duplicate_slice["groups"]))

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
        self.assertEqual(diagnostics["by_version_era"]["v1_0_20_to_1_0_23"], 2)
        self.assertEqual(diagnostics["by_version_era"]["legacy_unversioned"], 1)
        self.assertEqual(diagnostics["duplicate_market_key_count"], 1)
        self.assertEqual(diagnostics["duplicate_open_row_count"], 1)
        self.assertEqual(diagnostics["duplicate_open_row_count_legacy_era"], 1)
        self.assertEqual(diagnostics["duplicate_open_row_count_current_dedupe_era"], 0)
        self.assertEqual(diagnostics["duplicate_clusters"]["model_implied|btc-100k"], 2)
        self.assertEqual(diagnostics["duplicate_cluster_summaries"][0]["version_eras"], ["v1_0_20_to_1_0_23"])
        self.assertTrue(any("redundant duplicates" in warning for warning in diagnostics["warnings"]))

    def test_open_pick_diagnostics_tracks_esports_subdomain(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "topic": "Counter-Strike 2 markets to watch today",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "venue_market_key": "cs2-astr-g2",
                "model_probability": 0.53,
                "resolution_source": "polymarket",
                "skill_version": "1.0.40",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
            }
        ])

        self.assertEqual(diagnostics["by_domain"]["esports"], 1)
        self.assertEqual(diagnostics["by_subdomain"]["cs2"], 1)

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
        self.assertEqual(diagnostics["legacy_noisy_by_skill_version"]["1.0.18"], 1)
        self.assertEqual(diagnostics["legacy_noisy_by_pick_type"]["forecast"], 1)
        self.assertEqual(diagnostics["legacy_noisy_by_domain"]["macro"], 1)
        self.assertEqual(diagnostics["legacy_noisy_by_reason"]["promo_macro_or_crypto"], 1)
        self.assertEqual(diagnostics["legacy_noisy_examples"][0]["reason"], "promo_macro_or_crypto")
        self.assertTrue(any("legacy rationale text" in warning for warning in diagnostics["warnings"]))

    def test_open_pick_diagnostics_tracks_watchlist_scope_and_mixed_scope_clusters(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "topic": "NBA markets to watch today",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "venue_market_key": "nba-por-sas-series",
                "title": "NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                "question": "NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ",
                "skill_version": "1.0.33",
                "notes_json": json.dumps({"watchlist_scope": "series"}),
            },
            {
                "status": "open",
                "topic": "NBA markets to watch today",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "venue_market_key": "nba-por-sas-game",
                "title": "Trail Blazers vs. Spurs",
                "question": "Trail Blazers vs. Spurs",
                "skill_version": "1.0.33",
                "notes_json": json.dumps({"watchlist_scope": "game"}),
            },
        ])

        self.assertEqual(diagnostics["by_watchlist_scope"]["game"], 1)
        self.assertEqual(diagnostics["by_watchlist_scope"]["series"], 1)
        self.assertEqual(diagnostics["mixed_scope_clusters"][0]["series_title"], "NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers ")

    def test_open_pick_diagnostics_flags_legacy_sportsbook_and_recap_rationale(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "id": 50,
                "status": "open",
                "topic": "NBA matchups April 21 through April 23",
                "pick_type": "forecast",
                "venue": "polymarket",
                "title": "Trail Blazers vs. Spurs",
                "model_probability": 0.86,
                "resolution_source": "espn_nba",
                "skill_version": "1.0.30",
                "created_at": "2026-04-21 07:35:37",
                "evidence_json": json.dumps({"why_line": "NBA Playoffs: Trail Blazers vs. Spurs. The ATS Angle. Line: Spurs -11.5. Total: 220.0"}),
            },
            {
                "id": 51,
                "status": "open",
                "topic": "NBA matchups April 21 through April 23",
                "pick_type": "forecast",
                "venue": "polymarket",
                "title": "Magic vs. Pistons",
                "model_probability": 0.78,
                "resolution_source": "espn_nba",
                "skill_version": "1.0.30",
                "created_at": "2026-04-21 07:35:37",
                "evidence_json": json.dumps({"why_line": "Huge statement win Orlando Magic take down the No. 1 seed Detroit Pistons on Sunday. Orlando not backing down."}),
            },
        ])

        self.assertEqual(diagnostics["legacy_noisy_rationale_count"], 2)
        self.assertEqual(diagnostics["legacy_noisy_by_domain"]["nba"], 2)
        self.assertEqual(diagnostics["legacy_noisy_by_reason"]["sportsbook_copy"], 1)
        self.assertEqual(diagnostics["legacy_noisy_by_reason"]["sports_recap"], 1)
        self.assertEqual([row["id"] for row in diagnostics["legacy_noisy_examples"]], [50, 51])
        self.assertTrue(any("top legacy rationale failure mode" in warning.lower() for warning in diagnostics["warnings"]))

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

    def test_calibration_summary_excludes_legacy_sportsbook_rationale(self):
        summary = paper.calibration_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.04,
                "log_loss": 0.22,
                "model_probability": 0.80,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "forecast",
                "market_type": "game_outcome",
                "confidence": "moderate-low",
                "topic": "NBA matchups April 21 through April 23",
                "evidence_json": json.dumps({"why_line": "NBA Playoffs: Trail Blazers vs. Spurs. The ATS Angle. Line: Spurs -11.5. Total: 220.0"}),
            },
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.01,
                "log_loss": 0.10,
                "model_probability": 0.90,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "forecast",
                "market_type": "game_outcome",
                "confidence": "moderate-low",
                "topic": "NBA matchups April 21 through April 23",
                "evidence_json": json.dumps({"why_line": "Mostly market-driven right now; no clean injury, lineup, rest, or market-moving team signal surfaced in the last 24 hours."}),
            },
        ])

        self.assertEqual(summary["raw_resolved_count"], 2)
        self.assertEqual(summary["excluded_legacy_noisy_count"], 1)
        self.assertEqual(summary["count"], 1)

    def test_calibration_summary_groups_esports_subdomain(self):
        summary = paper.calibration_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.22,
                "log_loss": 0.55,
                "model_probability": 0.53,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "game_outcome",
                "confidence": "watchlist",
                "topic": "Counter-Strike 2 markets to watch today",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
                "evidence_json": json.dumps({"catalyst_summary": "Mostly market-driven right now."}),
            }
        ])

        self.assertEqual(summary["groups"]["domain:esports"]["count"], 1)
        self.assertEqual(summary["groups"]["subdomain:cs2"]["count"], 1)

    def test_calibration_summary_scope_filter_preserves_axes(self):
        summary = paper.calibration_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.10,
                "log_loss": 0.35,
                "model_probability": 0.72,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "forecast",
                "market_type": "game_outcome",
                "confidence": "moderate",
                "topic": "tomorrows nba games",
                "notes_json": json.dumps({"domain": "nba", "watchlist_scope": "game"}),
            },
            {
                "status": "resolved",
                "resolution_value": 0.0,
                "brier_score": 0.40,
                "log_loss": 0.80,
                "model_probability": 0.55,
                "venue": "kalshi",
                "anchor_source": "kalshi",
                "pick_type": "forecast",
                "market_type": "macro_binary",
                "confidence": "watchlist",
                "topic": "Fed rate cut by June",
                "notes_json": json.dumps({"domain": "macro"}),
            },
        ])

        groups = summary["groups"]
        for axis in ("venue", "anchor_source", "pick_type", "market_type", "confidence", "domain", "probability_bucket"):
            axis_keys = [key for key in groups if key.startswith(f"{axis}:")]
            self.assertTrue(axis_keys, f"expected {axis} groups")
            for key in axis_keys:
                row = groups[key]
                self.assertIn("count", row)
                self.assertIn("avg_probability", row)
                self.assertIn("observed_rate", row)
                self.assertIn("avg_brier", row)
        self.assertIn("domain:nba", groups)
        self.assertIn("domain:macro", groups)
        self.assertIn("watchlist_scope:game", groups)

    def test_calibration_summary_groups_future_subdomain_axes(self):
        summary = paper.calibration_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.18,
                "log_loss": 0.50,
                "model_probability": 0.60,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "game_outcome",
                "confidence": "watchlist",
                "topic": "Valorant markets to watch today",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant"}),
            },
            {
                "status": "resolved",
                "resolution_value": 0.0,
                "brier_score": 0.30,
                "log_loss": 0.70,
                "model_probability": 0.55,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "game_outcome",
                "confidence": "watchlist",
                "topic": "League of Legends markets to watch today",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "lol"}),
            },
        ])

        groups = summary["groups"]
        self.assertEqual(groups.get("subdomain:valorant", {}).get("count"), 1)
        self.assertEqual(groups.get("subdomain:lol", {}).get("count"), 1)

    def test_current_skill_comparable_summary_filters_pre_current_and_unversioned_rows(self):
        summary = paper.current_skill_comparable_summary([
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
                "skill_version": "1.0.28",
                "evidence_json": json.dumps({"why_line": "Official data release kept rate-cut pricing soft."}),
            },
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.09,
                "log_loss": 0.30,
                "model_probability": 0.70,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "crypto_daily",
                "confidence": "watchlist",
                "topic": "Bitcoin above 100k this week",
                "skill_version": "1.0.18",
                "evidence_json": json.dumps({"why_line": "Mostly market-driven right now; supporting evidence is thin."}),
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
                "skill_version": "",
                "evidence_json": json.dumps({"why_line": "BREAKING: top traders say this VIP macro call keeps cashing."}),
            },
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.16,
                "log_loss": 0.45,
                "model_probability": 0.60,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "weather_binary",
                "confidence": "watchlist",
                "topic": "NYC rain tomorrow",
                "skill_version": "",
                "evidence_json": json.dumps({"why_line": "Official NWS hourly forecast provides the current weather anchor."}),
            },
        ])

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["raw_resolved_count"], 4)
        self.assertEqual(summary["excluded_pre_current_version_count"], 1)
        self.assertEqual(summary["excluded_unversioned_count"], 1)

    def test_post_1_0_30_nba_watchlist_summary_groups_by_scope(self):
        summary = paper.post_1_0_30_nba_watchlist_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.04,
                "log_loss": 0.22,
                "model_probability": 0.80,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "game_outcome",
                "confidence": "watchlist",
                "topic": "NBA markets to watch today",
                "skill_version": "1.0.32",
                "notes_json": json.dumps({"watchlist_scope": "game"}),
                "evidence_json": json.dumps({"why_line": "Mostly market-driven right now; no clean injury, lineup, rest, or market-moving team signal surfaced in the last 24 hours."}),
            },
            {
                "status": "resolved",
                "resolution_value": 0.0,
                "brier_score": 0.36,
                "log_loss": 0.9,
                "model_probability": 0.60,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "futures",
                "confidence": "watchlist",
                "topic": "NBA markets to watch today",
                "skill_version": "1.0.32",
                "notes_json": json.dumps({"watchlist_scope": "series"}),
                "evidence_json": json.dumps({"why_line": "Mostly market-driven right now; supporting evidence is thin."}),
            },
        ])

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["groups"]["watchlist_scope:game"]["count"], 1)
        self.assertEqual(summary["groups"]["watchlist_scope:series"]["count"], 1)

    def test_post_1_0_38_esports_summary_groups_subdomain_and_empty_state(self):
        summary = paper.post_1_0_38_esports_summary([
            {
                "status": "resolved",
                "resolution_value": 1.0,
                "brier_score": 0.12,
                "log_loss": 0.33,
                "model_probability": 0.65,
                "venue": "polymarket",
                "anchor_source": "polymarket",
                "pick_type": "watchlist",
                "market_type": "game_outcome",
                "confidence": "watchlist",
                "topic": "Counter-Strike 2 markets to watch today",
                "skill_version": "1.0.40",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
                "evidence_json": json.dumps({"why_line": "Mostly market-driven right now."}),
            }
        ])

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["groups"]["domain:esports"]["count"], 1)
        self.assertEqual(summary["groups"]["subdomain:cs2"]["count"], 1)
        self.assertEqual(summary["pick_type_visibility"], ["watchlist"])
        self.assertEqual(summary["market_type_visibility"], ["game_outcome"])
        self.assertEqual(summary["missing_subdomain_count"], 0)
        self.assertEqual(summary["subdomain_visibility"], ["cs2"])

        empty = paper.post_1_0_38_esports_summary([])
        self.assertEqual(empty["count"], 0)
        self.assertIn("No resolved post-1.0.38 esports paper rows yet.", empty["empty_reason"])
        self.assertIn("no post-1.0.38 esports paper rows have resolved yet", empty["operator_note"].lower())
        self.assertEqual(empty["pick_type_visibility"], [])
        self.assertEqual(empty["market_type_visibility"], [])

    def test_open_pick_diagnostics_rolls_up_source_health_statuses(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "status": "open",
                "topic": "Bitcoin above 100k this week",
                "pick_type": "forecast",
                "venue": "model_implied",
                "model_probability": 0.12,
                "resolution_source": "",
                "skill_version": "1.0.28",
                "evidence_json": json.dumps({
                    "source_health": {
                        "source_status": {
                            "x": {"status": "degraded"},
                            "web": {"status": "empty"},
                        }
                    }
                }),
            }
        ])

        self.assertEqual(diagnostics["source_health_status_rollup"]["x"]["degraded"], 1)
        self.assertEqual(diagnostics["source_health_status_rollup"]["web"]["empty"], 1)

    def test_open_pick_diagnostics_exposes_esports_open_slice(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "id": 77,
                "status": "open",
                "topic": "Counter-Strike 2 matches today",
                "title": "Counter-Strike: Astralis vs G2 (BO3)",
                "pick_type": "forecast",
                "venue": "polymarket",
                "market_type": "esports_prop",
                "model_probability": 0.61,
                "resolution_source": "",
                "skill_version": "1.0.40",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
                "evidence_json": json.dumps({}),
            }
        ])

        self.assertEqual(diagnostics["esports_open_slice"]["count"], 1)
        self.assertEqual(diagnostics["esports_open_slice"]["by_pick_type"]["forecast"], 1)
        self.assertEqual(diagnostics["esports_open_slice"]["by_subdomain"]["cs2"], 1)
        self.assertEqual(diagnostics["esports_open_slice"]["by_market_type"]["esports_prop"], 1)
        self.assertEqual(diagnostics["esports_open_slice"]["missing_subdomain_count"], 0)
        self.assertEqual(diagnostics["esports_open_slice"]["rows"][0]["subdomain"], "cs2")

    def test_open_pick_diagnostics_flags_legacy_degraded_esports_rows(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "id": 85,
                "status": "open",
                "topic": "donk total kills markets to watch today",
                "title": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                "question": "NBA Playoffs: Rockets vs. Lakers Total Games O/U 5.5",
                "pick_type": "watchlist",
                "venue": "polymarket",
                "market_type": "player_prop",
                "model_probability": 0.82,
                "resolution_source": "polymarket",
                "skill_version": "1.0.62",
                "market_url": "https://polymarket.com/event/nba-playoffs-rockets-vs-lakers-total-games-ou-5pt5",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "cs2"}),
                "evidence_json": json.dumps({}),
            }
        ])

        flagged = diagnostics["esports_legacy_degraded_slice"]
        self.assertEqual(flagged["count"], 1)
        self.assertEqual(flagged["by_reason"]["non_esports_market"], 1)
        self.assertEqual(flagged["by_reason"]["unsupported_subdomain_label"], 1)
        self.assertEqual(flagged["by_reason"]["prop_contract_mismatch"], 1)
        self.assertEqual(flagged["rows"][0]["id"], 85)
        self.assertIn("audit-only samples", " ".join(diagnostics["warnings"]))

    def test_open_pick_diagnostics_exposes_named_prop_slice(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "id": 86,
                "status": "unknown",
                "topic": "TenZ total kills tonight",
                "title": "TenZ total kills tonight",
                "question": "TenZ total kills tonight",
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "market_type": "model_implied",
                "model_probability": 0.52,
                "resolution_source": "",
                "skill_version": "1.0.74",
                "market_url": "",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant", "degraded_reason_class": "no_matching_player_market"}),
                "evidence_json": json.dumps({}),
            }
        ])

        named_prop = diagnostics["esports_named_prop_slice"]
        self.assertEqual(named_prop["count"], 1)
        self.assertEqual(named_prop["by_subdomain"]["valorant"], 1)
        self.assertEqual(named_prop["by_market_type"]["model_implied"], 1)
        self.assertEqual(named_prop["by_anchor_source"]["model_implied"], 1)
        self.assertEqual(named_prop["by_degraded_reason_class"]["no_matching_player_market"], 1)
        self.assertEqual(named_prop["missing_degraded_reason_count"], 0)
        self.assertEqual(named_prop["rows"][0]["subdomain"], "valorant")

    def test_open_pick_diagnostics_flags_missing_named_prop_reason_metadata(self):
        diagnostics = paper.open_pick_diagnostics([
            {
                "id": 86,
                "status": "unknown",
                "topic": "TenZ total kills tonight",
                "title": "TenZ total kills tonight",
                "question": "TenZ total kills tonight",
                "pick_type": "forecast",
                "venue": "model_implied",
                "anchor_source": "model_implied",
                "market_type": "model_implied",
                "model_probability": 0.52,
                "resolution_source": "",
                "skill_version": "1.0.62",
                "market_url": "",
                "notes_json": json.dumps({"domain": "esports", "subdomain": "valorant"}),
                "evidence_json": json.dumps({}),
            }
        ])

        named_prop = diagnostics["esports_named_prop_slice"]
        self.assertEqual(named_prop["count"], 1)
        self.assertEqual(named_prop["missing_degraded_reason_count"], 1)
        self.assertEqual(named_prop["by_degraded_reason_class"]["missing"], 1)


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
