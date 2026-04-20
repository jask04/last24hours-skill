import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from scripts.lib import closing_soon, market_watchlist, query_type, render, schema, sports_schedule


def _market_event(
    slug: str,
    title: str,
    end_date: str,
    *,
    liquidity: float = 50_000,
    volume: float = 25_000,
    prices=None,
    spread: float = 0.02,
    active: bool = True,
    closed: bool = False,
):
    prices = prices or [0.55, 0.45]
    return {
        "id": slug,
        "slug": slug,
        "title": title,
        "active": active,
        "closed": closed,
        "liquidity": liquidity,
        "volume24hr": volume,
        "volume1mo": volume,
        "updatedAt": "2026-04-19T21:00:00Z",
        "markets": [
            {
                "id": f"{slug}-m",
                "question": title,
                "active": active,
                "closed": closed,
                "liquidity": liquidity,
                "volume": volume,
                "volume24hr": volume,
                "outcomes": json.dumps(["Yes", "No"]),
                "outcomePrices": json.dumps(prices),
                "bestBid": max(0.0, prices[0] - spread / 2),
                "bestAsk": min(1.0, prices[0] + spread / 2),
                "spread": spread,
                "endDate": end_date,
            }
        ],
    }


def _espn_event(league_title: str, state: str = "in"):
    return {
        "name": f"Away {league_title} at Home {league_title}",
        "date": "2026-04-20T02:30:00Z",
        "competitions": [
            {
                "status": {
                    "period": 2,
                    "displayClock": "04:12",
                    "type": {"state": state, "detail": "2nd Quarter"},
                },
                "competitors": [
                    {"homeAway": "home", "score": "51", "team": {"displayName": f"Home {league_title}", "shortDisplayName": "Home", "abbreviation": "HME"}},
                    {"homeAway": "away", "score": "47", "team": {"displayName": f"Away {league_title}", "shortDisplayName": "Away", "abbreviation": "AWY"}},
                ],
            }
        ],
    }


class ClosingSoonTests(unittest.TestCase):
    def test_closing_soon_prompts_route_to_market_watchlist(self):
        self.assertEqual(query_type.detect_query_type("Polymarket markets closing soon"), "market_watchlist")
        self.assertEqual(query_type.detect_query_type("live sports games on Polymarket right now"), "market_watchlist")

    def test_scanner_keeps_end_datetime_and_minutes_to_close(self):
        now = datetime(2026, 4, 20, 4, 0, tzinfo=timezone.utc)
        event = _market_event("btc-daily", "Bitcoin Up or Down on April 19?", "2026-04-20T06:00:00Z")
        with mock.patch("scripts.lib.closing_soon.polymarket.search_polymarket", return_value={"events": [event]}):
            items = closing_soon.scan_polymarket_closing_soon(
                "crypto markets closing soon tonight",
                "2026-04-19",
                "2026-04-19",
                now=now,
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["end_datetime"], "2026-04-20T06:00:00Z")
        self.assertEqual(items[0]["minutes_to_close"], 120.0)
        self.assertEqual(items[0]["closing_soon_reason"], "closing_soon")
        self.assertEqual(items[0]["market_type"], "crypto_daily")

    def test_scanner_excludes_expired_closed_no_liquidity_and_effectively_settled(self):
        now = datetime(2026, 4, 20, 4, 0, tzinfo=timezone.utc)
        events = [
            _market_event("expired", "Bitcoin expired", "2026-04-20T03:00:00Z"),
            _market_event("closed", "Bitcoin closed", "2026-04-20T06:00:00Z", closed=True),
            _market_event("no-liq", "Bitcoin no liquidity", "2026-04-20T06:00:00Z", liquidity=0),
            _market_event("settled", "Bitcoin settled", "2026-04-20T06:00:00Z", prices=[0.995, 0.005], spread=0.0),
            _market_event("valid", "Bitcoin valid", "2026-04-20T06:00:00Z", prices=[0.62, 0.38]),
        ]
        with mock.patch("scripts.lib.closing_soon.polymarket.search_polymarket", return_value={"events": events}):
            items = closing_soon.scan_polymarket_closing_soon("crypto markets closing soon", "2026-04-19", "2026-04-19", now=now)

        self.assertEqual([item["title"] for item in items], ["Bitcoin valid"])

    def test_near_expiry_watchlist_ranks_above_long_dated_market(self):
        report = schema.Report(
            topic="Polymarket markets closing soon",
            range_from="2026-04-19",
            range_to="2026-04-19",
            generated_at="2026-04-19T21:00:00-07:00",
            mode="both",
            planning_notes=["closing_soon"],
        )
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Near close market",
                question="Will Bitcoin be up today?",
                url="https://polymarket.com/event/near",
                outcome_prices=[("Yes", 0.56), ("No", 0.44)],
                engagement=schema.Engagement(volume=20_000, liquidity=30_000),
                market_signal_quality=0.55,
                volume_24h=20_000,
                spread=0.02,
                relevance=0.8,
                minutes_to_close=45.0,
                closing_soon_reason="closing_soon",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Long dated IPO market",
                question="Will a company IPO this year?",
                url="https://polymarket.com/event/ipo",
                outcome_prices=[("Yes", 0.58), ("No", 0.42)],
                engagement=schema.Engagement(volume=500_000, liquidity=500_000),
                market_signal_quality=0.9,
                volume_24h=500_000,
                spread=0.02,
                relevance=0.9,
                minutes_to_close=700.0,
                closing_soon_reason="closing_soon",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].source_item_id, "PM1")
        self.assertIn("closing soon", items[0].why_ranks)

    def test_espn_live_game_parser_handles_major_leagues(self):
        now = datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc)
        games = [
            sports_schedule._parse_live_game(league, _espn_event(league.upper()), now, 60)
            for league in ("nba", "mlb", "nhl", "nfl")
        ]

        self.assertEqual([game.league for game in games], ["nba", "mlb", "nhl", "nfl"])
        self.assertTrue(all(game.is_live for game in games))
        self.assertTrue(all("47" in game.context and "51" in game.context for game in games))
        self.assertTrue(all(game.home_abbreviation == "HME" and game.away_abbreviation == "AWY" for game in games))
        self.assertIn("AWY at HME", games[0].live_search_aliases)

    def test_live_sports_label_requires_matching_market(self):
        now = datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc)
        live_game = sports_schedule.LiveGame(
            league="nba",
            matchup="Los Angeles Lakers at Houston Rockets",
            home_team="Houston Rockets",
            away_team="Los Angeles Lakers",
            start_time="2026-04-20T01:30:00Z",
            status_state="in",
            status_detail="3rd Quarter",
            home_short_name="Rockets",
            away_short_name="Lakers",
            home_abbreviation="HOU",
            away_abbreviation="LAL",
            home_score=82,
            away_score=78,
        )
        diagnostics = {}
        events = [
            _market_event("nba-lal-hou", "LAL vs HOU", "2026-04-20T05:30:00Z"),
            _market_event("nba-lal-hou-series", "NBA Playoffs: Who Will Win Series? - Lakers vs. Rockets", "2026-05-04T00:00:00Z"),
            _market_event("bos-phi", "Celtics vs. 76ers", "2026-04-20T05:30:00Z"),
        ]
        with mock.patch("scripts.lib.closing_soon.polymarket.search_polymarket", return_value={"events": events}):
            items = closing_soon.scan_polymarket_closing_soon(
                "live sports games on Polymarket right now",
                "2026-04-19",
                "2026-04-19",
                live_games=[live_game],
                now=now,
                diagnostics=diagnostics,
            )

        live_items = [item for item in items if item.get("closing_soon_reason") == "live_sports"]
        self.assertEqual(len(live_items), 1)
        self.assertEqual(live_items[0]["title"], "LAL vs HOU")
        self.assertIn("Rockets", live_items[0]["live_game_context"])
        self.assertEqual(live_items[0]["live_game_league"], "nba")
        self.assertGreaterEqual(live_items[0]["live_match_confidence"], 0.8)
        self.assertEqual(live_items[0]["live_match_reason"], "direct_match")
        self.assertNotIn("NBA Playoffs", {item["title"] for item in items})
        self.assertEqual(diagnostics["live_polymarket_matches"], 1)
        self.assertEqual(diagnostics["live_reject_reasons"]["series_market"], 1)
        self.assertEqual(diagnostics["live_reject_reasons"]["wrong_matchup"], 1)

    def test_live_direct_games_rank_above_starting_soon_and_generic_closing(self):
        report = schema.Report(
            topic="live sports games on Polymarket right now",
            range_from="2026-04-19",
            range_to="2026-04-19",
            generated_at="2026-04-19T21:00:00-07:00",
            mode="both",
            planning_notes=["closing_soon", "live-games:2"],
        )
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Generic closing market",
                question="Bitcoin Up or Down?",
                url="https://polymarket.com/event/btc",
                outcome_prices=[("Up", 0.51), ("Down", 0.49)],
                engagement=schema.Engagement(volume=500_000, liquidity=500_000),
                market_signal_quality=0.95,
                volume_24h=500_000,
                spread=0.01,
                relevance=0.95,
                minutes_to_close=10,
                closing_soon_reason="closing_soon",
            ),
            schema.PolymarketItem(
                id="PM2",
                title="Starting soon game",
                question="Celtics vs. 76ers",
                url="https://polymarket.com/event/nba-bos-phi",
                outcome_prices=[("Celtics", 0.61), ("76ers", 0.39)],
                engagement=schema.Engagement(volume=20_000, liquidity=20_000),
                market_signal_quality=0.5,
                volume_24h=20_000,
                spread=0.03,
                relevance=0.8,
                minutes_to_close=180,
                closing_soon_reason="starting_soon",
                live_game_context="NBA 7:00 PM ET",
            ),
            schema.PolymarketItem(
                id="PM3",
                title="Live game",
                question="Lakers vs. Rockets",
                url="https://polymarket.com/event/nba-lal-hou",
                outcome_prices=[("Rockets", 0.57), ("Lakers", 0.43)],
                engagement=schema.Engagement(volume=10_000, liquidity=10_000),
                market_signal_quality=0.45,
                volume_24h=10_000,
                spread=0.04,
                relevance=0.75,
                minutes_to_close=240,
                closing_soon_reason="live_sports",
                live_game_context="NBA 3rd Quarter; Lakers 78, Rockets 82",
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual([item.source_item_id for item in items], ["PM3", "PM2"])

    def test_live_sports_no_game_and_no_market_messages_are_distinct(self):
        no_games = schema.Report(
            topic="live sports games on Polymarket right now",
            range_from="2026-04-19",
            range_to="2026-04-19",
            generated_at="2026-04-19T21:00:00-07:00",
            mode="both",
            planning_notes=["closing_soon", "live-games:0", "live-polymarket-matches:0"],
        )
        no_market = schema.Report(
            topic="live sports games on Polymarket right now",
            range_from="2026-04-19",
            range_to="2026-04-19",
            generated_at="2026-04-19T21:00:00-07:00",
            mode="both",
            planning_notes=["closing_soon", "live-games:2", "live-polymarket-matches:0"],
        )

        self.assertIn("ESPN found no live or starting-soon", render.render_compact(no_games))
        self.assertIn("ESPN found 2 live/starting-soon game(s)", render.render_compact(no_market))


if __name__ == "__main__":
    unittest.main()
