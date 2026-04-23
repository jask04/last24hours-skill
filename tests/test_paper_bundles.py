import json
import os
import unittest
from unittest import mock

from scripts import paper
from scripts.lib import forecast_plan, market_watchlist, paper_bundles, query_type, render, schema, sports_schedule


def _espn_event(name: str, home: str, away: str, date_value: str, state: str = "pre"):
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "date": date_value,
        "competitions": [
            {
                "status": {
                    "period": 0,
                    "displayClock": "",
                    "type": {"state": state, "detail": "Scheduled" if state == "pre" else "Final"},
                },
                "competitors": [
                    {"homeAway": "home", "score": "0", "team": {"displayName": home, "shortDisplayName": home.split()[-1], "abbreviation": home[:3].upper()}},
                    {"homeAway": "away", "score": "0", "team": {"displayName": away, "shortDisplayName": away.split()[-1], "abbreviation": away[:3].upper()}},
                ],
            }
        ],
    }


def _watch_item(idx: int, title: str, outcome: str, probability: float, *, teams_context: str = ""):
    return schema.MarketWatchItem(
        id=f"MW{idx}",
        title=title,
        question=title,
        venue="Polymarket",
        url=f"https://polymarket.com/event/{idx}",
        outcome_label=outcome,
        probability=probability,
        implied_probability=probability,
        spread=0.03,
        market_type="game_outcome",
        liquidity=20_000,
        volume=50_000,
        rank_score=65 - idx,
        why_ranks="usable market signal",
        source_item_id=f"PM{idx}",
        live_game_context=teams_context,
        live_game_league="nba" if teams_context else "",
        live_match_confidence=0.85 if teams_context else None,
        live_match_reason="direct_match" if teams_context else "",
    )


class PaperBundleTests(unittest.TestCase):
    def test_parlay_prompt_routes_to_market_watchlist(self):
        self.assertEqual(
            query_type.detect_query_type("NBA paper parlay ideas April 20 through April 22"),
            "market_watchlist",
        )

    def test_nba_date_window_parsing_explicit_and_relative(self):
        with mock.patch.dict(os.environ, {"LAST24HOURS_AS_OF_DATE": "2026-04-20"}):
            self.assertEqual(
                sports_schedule.resolve_nba_date_window("NBA games April 20 2026 through April 22 2026"),
                ("20260420", "20260422"),
            )
            self.assertEqual(
                sports_schedule.resolve_nba_date_window("NBA paper bundle today through Wednesday"),
                ("20260420", "20260422"),
            )
            self.assertEqual(
                sports_schedule.resolve_nba_date_window("NBA paper bundle next 2 days"),
                ("20260421", "20260422"),
            )

    def test_nba_date_window_expands_espn_slate(self):
        def fake_get(url, timeout=15, retries=2):
            if "20260420" in url:
                return {"events": [_espn_event("Los Angeles Lakers at Houston Rockets", "Houston Rockets", "Los Angeles Lakers", "2026-04-20T23:30:00Z")]}
            if "20260421" in url:
                return {"events": [_espn_event("Boston Celtics at New York Knicks", "New York Knicks", "Boston Celtics", "2026-04-21T23:30:00Z")]}
            return {"events": []}

        with mock.patch("scripts.lib.sports_schedule.http.get", side_effect=fake_get):
            start, end, games = sports_schedule.expand_nba_date_window_query("NBA games April 20 2026 through April 21 2026")

        self.assertEqual((start, end), ("20260420", "20260421"))
        self.assertEqual([game.matchup for game in games], ["Los Angeles Lakers at Houston Rockets", "Boston Celtics at New York Knicks"])
        self.assertIn("start 2026-04-20T23:30:00Z", games[0].context)
        self.assertNotIn(" 0, ", games[0].context)
        self.assertNotIn("period 0", games[0].context)
        self.assertNotIn("0.0", games[0].context)

    def test_espn_live_context_keeps_score_and_clock(self):
        game = sports_schedule.LiveGame(
            league="nba",
            matchup="Los Angeles Lakers at Houston Rockets",
            home_team="Houston Rockets",
            away_team="Los Angeles Lakers",
            start_time="2026-04-20T23:30:00Z",
            status_state="in",
            status_detail="3rd Quarter",
            period=3,
            clock="04:12",
            home_score=82,
            away_score=78,
        )

        self.assertIn("Los Angeles Lakers 78, Houston Rockets 82", game.context)
        self.assertIn("period 3 04:12", game.context)

    def test_planner_preserves_quick_window_topics_up_to_cap(self):
        topics = [f"Team {idx} at Other {idx}" for idx in range(8)]
        plan = forecast_plan.build_plan("NBA games April 20 through April 22", "prediction", "quick", search_topics=topics)

        self.assertEqual(len(plan.search_topics), 6)
        self.assertEqual(plan.search_topics[:2], topics[:2])

    def test_game_matcher_requires_both_teams(self):
        game = sports_schedule.LiveGame(
            league="nba",
            matchup="Los Angeles Lakers at Houston Rockets",
            home_team="Houston Rockets",
            away_team="Los Angeles Lakers",
            start_time="2026-04-20T23:30:00Z",
            status_state="pre",
            status_detail="Scheduled",
            home_short_name="Rockets",
            away_short_name="Lakers",
            home_abbreviation="HOU",
            away_abbreviation="LAL",
        )

        match, confidence, reason = sports_schedule.match_game_for_market_text("LAL vs HOU game outcome", [game])

        self.assertEqual(match.matchup, game.matchup)
        self.assertGreaterEqual(confidence, 0.8)
        self.assertEqual(reason, "direct_match")
        self.assertIsNone(sports_schedule.match_game_for_market_text("Lakers season series", [game])[0])

    def test_bundle_generation_uses_balanced_direct_game_legs(self):
        report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.58, teams_context="NBA Scheduled"),
            _watch_item(2, "Celtics vs. Knicks", "Celtics", 0.55, teams_context="NBA Scheduled"),
            _watch_item(3, "Nuggets vs. Timberwolves", "Nuggets", 0.62, teams_context="NBA Scheduled"),
        ]

        bundles, reason = paper_bundles.synthesize_paper_bundles(report)

        self.assertEqual(reason, "")
        self.assertTrue(bundles)
        self.assertEqual(len(bundles[0].legs), 2)
        self.assertAlmostEqual(bundles[0].combined_probability_independence, 0.319, places=3)
        self.assertIn("independence baseline", bundles[0].correlation_warning.lower())
        self.assertEqual(bundles[0].legs[0].game_key, "lakers|rockets")

    def test_bundle_generation_rejects_favorite_only_and_team_overlap(self):
        favorite_report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        favorite_report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.91, teams_context="NBA Scheduled"),
            _watch_item(2, "Celtics vs. Knicks", "Celtics", 0.92, teams_context="NBA Scheduled"),
        ]
        bundles, reason = paper_bundles.synthesize_paper_bundles(favorite_report)
        self.assertEqual(bundles, [])
        self.assertIn("too few direct NBA game-outcome", reason)

        overlap_report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        overlap_report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.58, teams_context="NBA Scheduled"),
            _watch_item(2, "Lakers vs. Warriors", "Warriors", 0.57, teams_context="NBA Scheduled"),
        ]
        bundles, reason = paper_bundles.synthesize_paper_bundles(overlap_report)
        self.assertEqual(bundles, [])
        self.assertIn("same-game or same-team overlap", reason)

    def test_bundle_generation_requires_trusted_espn_context(self):
        report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.58),
            _watch_item(2, "Celtics vs. Knicks", "Celtics", 0.55, teams_context="NBA Scheduled"),
        ]

        bundles, reason = paper_bundles.synthesize_paper_bundles(report)

        self.assertEqual(bundles, [])
        self.assertIn("trusted ESPN", reason)

    def test_bundle_generation_rejects_live_games(self):
        report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.58, teams_context="NBA 3rd Quarter; Los Angeles Lakers 78, Houston Rockets 82; period 3 04:12"),
            _watch_item(2, "Celtics vs. Knicks", "Celtics", 0.55, teams_context="NBA Scheduled; start 2026-04-21T23:30:00Z"),
            _watch_item(3, "Nuggets vs. Timberwolves", "Nuggets", 0.60, teams_context="NBA Scheduled; start 2026-04-21T01:00:00Z"),
        ]

        bundles, reason = paper_bundles.synthesize_paper_bundles(report)

        self.assertTrue(bundles)
        self.assertTrue(all("3rd Quarter" not in leg.live_game_context for leg in bundles[0].legs))
        self.assertNotIn("already live", reason)

    def test_bundle_generation_reports_no_future_games_when_window_is_empty(self):
        report = schema.Report(
            topic="NBA paper bundle next 2 days",
            range_from="2026-04-20",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
            planning_notes=["nba-window-games:0"],
        )

        bundles, reason = paper_bundles.synthesize_paper_bundles(report)

        self.assertEqual(bundles, [])
        self.assertEqual(reason, "no future NBA games found in the requested bundle window.")

    def test_bundle_intent_watchlist_only_keeps_direct_espn_game_markets(self):
        report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Raptors vs. Cavaliers",
                question="Raptors vs. Cavaliers",
                url="https://polymarket.com/event/nba-tor-cle-2026-04-20",
                outcome_prices=[("Cavaliers", 0.79), ("Raptors", 0.21)],
                engagement=schema.Engagement(volume=100_000, liquidity=100_000),
                market_signal_quality=0.80,
                spread=0.01,
                market_type="game_outcome",
                live_game_context="NBA Scheduled; start 2026-04-20T23:00Z",
                live_game_league="nba",
                live_match_confidence=0.85,
                live_match_reason="direct_match",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers",
                question="NBA Playoffs: Who Will Win Series? - Spurs vs. Trail Blazers",
                url="https://polymarket.com/event/nba-playoffs-who-will-win-series-spurs-vs-trail-blazers",
                outcome_prices=[("Spurs", 0.96), ("Blazers", 0.04)],
                engagement=schema.Engagement(volume=100_000, liquidity=100_000),
                market_signal_quality=0.90,
                spread=0.01,
                market_type="futures",
            ),
            schema.PolymarketItem(
                id="PM3",
                title="NBA Playoffs: Spurs vs. Trail Blazers Total Games O/U 4.5",
                question="NBA Playoffs: Spurs vs. Trail Blazers Total Games O/U 4.5",
                url="https://polymarket.com/event/nba-playoffs-trail-blazers-vs-spurs-total-games-ou-4pt5",
                outcome_prices=[("Over 4.5", 0.59), ("Under 4.5", 0.41)],
                engagement=schema.Engagement(volume=100_000, liquidity=100_000),
                market_signal_quality=0.90,
                spread=0.01,
                market_type="player_prop",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual([item.source_item_id for item in items], ["PM1"])

    def test_bundle_rendering_and_schema_round_trip(self):
        report = schema.Report(
            topic="NBA paper parlay ideas April 20 through April 22",
            range_from="2026-04-19",
            range_to="2026-04-20",
            generated_at="2026-04-20T12:00:00Z",
            mode="both",
        )
        report.market_watchlist = [
            _watch_item(1, "Lakers vs. Rockets", "Lakers", 0.58, teams_context="NBA Scheduled"),
            _watch_item(2, "Celtics vs. Knicks", "Celtics", 0.55, teams_context="NBA Scheduled"),
        ]
        report.paper_bundles, report.paper_bundle_reason = paper_bundles.synthesize_paper_bundles(report)

        restored = schema.Report.from_dict(report.to_dict())
        output = render.render_compact(restored)

        self.assertEqual(restored.paper_bundles[0].legs[0].outcome_label, "Lakers")
        self.assertIn("Paper Bundles", output)
        self.assertIn("Independence baseline", output)
        self.assertIn("Game status: NBA Scheduled", output)
        self.assertNotIn("Live game: NBA Scheduled", output)
        lowered = output.lower()
        for banned in ("stake", "lock", "tail", "guaranteed", "you should bet", "parlay", "market picks", "pick:"):
            self.assertNotIn(banned, lowered)

    def test_paper_extraction_records_bundle_notes_json(self):
        report = {
            "topic": "NBA paper parlay ideas April 20 through April 22",
            "query_type": "market_watchlist",
            "paper_bundles": [
                {
                    "id": "PB1",
                    "title": "Paper Bundle 1",
                    "combined_probability_independence": 0.319,
                    "confidence_bucket": "low-moderate",
                    "correlation_warning": "Rough independence baseline only.",
                    "rationale": "Direct game markets.",
                    "fragility": "Lineup changes.",
                    "legs": [
                        {"venue": "Polymarket", "source_item_id": "PM1", "outcome_label": "Lakers", "probability": 0.58, "url": "https://polymarket.com/event/a"},
                        {"venue": "Polymarket", "source_item_id": "PM2", "outcome_label": "Celtics", "probability": 0.55, "url": "https://polymarket.com/event/b"},
                    ],
                }
            ],
        }

        picks = [pick for pick in paper.extract_paper_picks(report) if pick["pick_type"] == "bundle"]

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["venue"], "paper_bundle")
        self.assertEqual(picks[0]["status"], "unknown")
        notes = json.loads(picks[0]["notes_json"])
        self.assertTrue(notes["paper_only"])
        self.assertEqual(notes["combined_probability_independence"], 0.319)
        self.assertEqual(len(notes["legs"]), 2)


if __name__ == "__main__":
    unittest.main()
