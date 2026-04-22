import unittest

from scripts import last24hours
from scripts.lib import forecast, schema


def _engagement(volume=75_000, liquidity=0, open_interest=200_000):
    return schema.Engagement(volume=volume, liquidity=liquidity, open_interest=open_interest)


def _nba_slate_report(topic: str, from_date: str, to_date: str) -> schema.Report:
    return schema.Report(
        topic=topic,
        range_from=from_date,
        range_to=to_date,
        generated_at=f"{to_date}T00:00:00+00:00",
        mode="both",
    )


class KalshiNbaSlateRegressionTests(unittest.TestCase):
    def test_team_code_matchup_matches_full_team_name_topic(self):
        item = {
            "title": "Game 4: Phoenix at Oklahoma City",
            "question": "Game 4: Phoenix at Oklahoma City Winner?",
            "ticker": "KXNBAGAME-26APR22PHXOKC-OKC",
            "event_ticker": "KXNBAGAME-26APR22PHXOKC",
        }
        self.assertTrue(
            last24hours._market_matches_matchup(item, "Phoenix Suns vs Oklahoma City Thunder")
        )

    def test_team_code_matchup_rejects_wrong_opponent(self):
        item = {
            "title": "Game 4: Phoenix at Oklahoma City",
            "question": "Game 4: Phoenix at Oklahoma City Winner?",
            "ticker": "KXNBAGAME-26APR22PHXOKC-OKC",
            "event_ticker": "KXNBAGAME-26APR22PHXOKC",
        }
        self.assertFalse(
            last24hours._market_matches_matchup(item, "Phoenix Suns vs Dallas Mavericks")
        )

    def test_stale_kalshi_ticker_rejected_for_tomorrow_slate_date(self):
        kalshi_item = schema.KalshiItem(
            id="KA-stale",
            title="Game 3: New York at Atlanta",
            question="Game 3: New York at Atlanta Winner?",
            url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR20NYKATL-NYK",
            ticker="KXNBAGAME-26APR20NYKATL-NYK",
            event_ticker="KXNBAGAME-26APR20NYKATL",
            current_probability=0.55,
            market_type="game_outcome",
        )
        self.assertFalse(forecast._sports_market_date_compatible(kalshi_item, "2026-04-22"))

    def test_fresh_kalshi_ticker_accepted_for_matching_slate_date(self):
        kalshi_item = schema.KalshiItem(
            id="KA-fresh",
            title="Game 3: New York at Atlanta",
            question="Game 3: New York at Atlanta Winner?",
            url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22NYKATL-NYK",
            ticker="KXNBAGAME-26APR22NYKATL-NYK",
            event_ticker="KXNBAGAME-26APR22NYKATL",
            current_probability=0.55,
            market_type="game_outcome",
        )
        self.assertTrue(forecast._sports_market_date_compatible(kalshi_item, "2026-04-22"))

    def test_kalshi_only_single_matchup_forecast_anchors_to_kalshi(self):
        report = _nba_slate_report("Phoenix Suns at Oklahoma City Thunder tomorrow", "2026-04-21", "2026-04-21")
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Game 4: Phoenix at Oklahoma City",
                question="Game 4: Phoenix at Oklahoma City Winner?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22PHXOKC-OKC",
                ticker="KXNBAGAME-26APR22PHXOKC-OKC",
                event_ticker="KXNBAGAME-26APR22PHXOKC",
                current_probability=0.93,
                implied_probability=0.93,
                best_bid=0.92,
                best_ask=0.93,
                spread=0.01,
                movement_24h=-0.5,
                volume_24h=60_000,
                market_signal_quality=0.6,
                market_type="game_outcome",
                date="2026-04-18",
                date_confidence="high",
                engagement=_engagement(),
                end_date="2026-05-07",
                relevance=0.75,
                score=80,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0].anchor_source, "kalshi")

    def test_mixed_kalshi_and_polymarket_slate_surfaces_both_games_by_score(self):
        report = _nba_slate_report("tomorrows nba games", "2026-04-21", "2026-04-21")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Phoenix Suns vs. Oklahoma City Thunder",
                question="Phoenix Suns vs. Oklahoma City Thunder",
                url="https://polymarket.com/event/nba-phx-okc-2026-04-22",
                outcome_prices=[("Phoenix Suns", 0.07), ("Oklahoma City Thunder", 0.93)],
                engagement=schema.Engagement(volume=1_000_000, liquidity=300_000),
                market_type="game_outcome",
                relevance=0.95,
                score=95,
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA2",
                title="Game 2: Orlando at Detroit",
                question="Game 2: Orlando at Detroit Winner?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR22ORLDET-DET",
                ticker="KXNBAGAME-26APR22ORLDET-DET",
                event_ticker="KXNBAGAME-26APR22ORLDET",
                current_probability=0.86,
                implied_probability=0.86,
                best_bid=0.85,
                best_ask=0.86,
                spread=0.01,
                movement_24h=1.0,
                volume_24h=54_210.0,
                market_signal_quality=0.61,
                market_type="game_outcome",
                date="2026-04-18",
                date_confidence="high",
                engagement=_engagement(volume=54_210.0, open_interest=95_000.0),
                end_date="2026-05-07",
                relevance=0.72,
                score=70,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 2)
        anchor_sources = {item.anchor_source for item in forecasts}
        self.assertIn("polymarket", anchor_sources)
        self.assertIn("kalshi", anchor_sources)
        self.assertGreaterEqual(
            next(item for item in forecasts if item.anchor_source == "polymarket").forecast_probability,
            next(item for item in forecasts if item.anchor_source == "kalshi").forecast_probability - 1,
        )
        self.assertEqual(forecasts[0].anchor_source, "polymarket")


if __name__ == "__main__":
    unittest.main()
