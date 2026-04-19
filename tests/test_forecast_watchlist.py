import unittest

from scripts.lib import forecast, market_watchlist, schema


def _report(topic: str) -> schema.Report:
    return schema.Report(
        topic=topic,
        range_from="2026-04-10",
        range_to="2026-04-11",
        generated_at="2026-04-11T00:00:00+00:00",
        mode="both",
    )


def _engagement(volume=1_000_000, liquidity=250_000, open_interest=None):
    return schema.Engagement(volume=volume, liquidity=liquidity, open_interest=open_interest)


class ForecastWatchlistTests(unittest.TestCase):
    def test_nba_slate_ignores_player_props_as_forecasts(self):
        report = _report("todays nba games")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Thunder vs. Nuggets",
                question="Christian Braun: Assists O/U 0.5",
                url="https://polymarket.com/event/nba-okc-den-2026-04-10",
                outcome_prices=[("Yes", 0.0), ("No", 1.0)],
                engagement=_engagement(),
                market_type="player_prop",
                relevance=0.9,
                score=95,
            )
        ]

        self.assertEqual(forecast.synthesize_forecasts(report), [])

    def test_nba_watchlist_labels_player_props_explicitly(self):
        report = _report("NBA markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Thunder vs. Nuggets",
                question="Christian Braun: Assists O/U 0.5",
                url="https://polymarket.com/event/nba-okc-den-2026-04-10",
                outcome_prices=[("Yes", 0.54), ("No", 0.46)],
                engagement=_engagement(),
                market_type="player_prop",
                market_signal_quality=0.82,
                volume_24h=500_000,
                best_bid=0.53,
                best_ask=0.55,
                spread=0.02,
                movement_24h=2.5,
                relevance=0.95,
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].market_type, "player_prop")
        self.assertIn("player prop", items[0].why_ranks)
        self.assertEqual(items[0].title, "Christian Braun: Assists O/U 0.5")

    def test_near_certain_threshold_market_is_suppressed_without_strong_unresolved_signal(self):
        report = _report("crypto prediction markets to watch today")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above ___ on April 11?",
                question="Will the price of Bitcoin be above $64,000 on April 11?",
                url="https://polymarket.com/event/bitcoin-above-on-april-11",
                outcome_prices=[("Yes", 1.0), ("No", 0.0)],
                engagement=_engagement(volume=2_000_000, liquidity=800_000),
                market_type="threshold",
                market_signal_quality=0.86,
                volume_24h=2_000_000,
                best_bid=1.0,
                best_ask=1.0,
                spread=0.0,
                movement_24h=0.9,
                relevance=0.9,
                score=95,
            )
        ]

        self.assertEqual(market_watchlist.synthesize_market_watchlist(report), [])

    def test_crypto_threshold_forecast_rejects_conflicting_threshold_markets(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above ___ on April 19?",
                question="Will the price of Bitcoin be above $70,000 on April 19?",
                url="https://polymarket.com/event/bitcoin-above-on-april-19",
                outcome_prices=[("Yes", 1.0), ("No", 0.0)],
                engagement=_engagement(volume=2_000_000, liquidity=600_000),
                market_type="threshold",
                relevance=0.95,
                score=99,
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Bitcoin price range on Apr 19, 2026 at 5pm EDT?",
                question="Bitcoin price range on Apr 19, 2026?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC-26APR1917-B75875",
                ticker="KXBTC-26APR1917-B75875",
                event_ticker="KXBTC-26APR1917",
                series_ticker="KXBTC",
                current_probability=0.08,
                engagement=_engagement(volume=2_942, liquidity=0, open_interest=2_748),
                market_type="threshold",
                relevance=0.8,
                score=80,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(len(forecasts), 1)
        self.assertIsNone(forecasts[0].polymarket_market_id)
        self.assertIsNone(forecasts[0].kalshi_market_id)
        self.assertEqual(forecasts[0].anchor_source, "model_implied")

    def test_crypto_threshold_forecast_keeps_matching_threshold_market(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above $100,000 this week?",
                question="Will the price of Bitcoin be above $100,000 this week?",
                url="https://polymarket.com/event/bitcoin-above-100k-this-week",
                outcome_prices=[("Yes", 0.22), ("No", 0.78)],
                engagement=_engagement(volume=800_000, liquidity=250_000),
                market_type="threshold",
                relevance=0.95,
                score=95,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.78)

    def test_crypto_threshold_forecast_does_not_blend_incompatible_kalshi_market(self):
        report = _report("Bitcoin above 100k this week")
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin above $100,000 this week?",
                question="Will the price of Bitcoin be above $100,000 this week?",
                url="https://polymarket.com/event/bitcoin-above-100k-this-week",
                outcome_prices=[("Yes", 0.22), ("No", 0.78)],
                engagement=_engagement(volume=800_000, liquidity=250_000),
                market_type="threshold",
                relevance=0.95,
                score=95,
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Bitcoin price range on Apr 19, 2026 at 5pm EDT?",
                question="Bitcoin price range on Apr 19, 2026?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC-26APR1917-B75875",
                ticker="KXBTC-26APR1917-B75875",
                event_ticker="KXBTC-26APR1917",
                series_ticker="KXBTC",
                current_probability=0.08,
                engagement=_engagement(volume=2_942, liquidity=0, open_interest=2_748),
                market_type="threshold",
                relevance=0.8,
                score=80,
            )
        ]

        forecasts = forecast.synthesize_forecasts(report)

        self.assertEqual(forecasts[0].anchor_source, "polymarket")
        self.assertEqual(forecasts[0].polymarket_market_id, "PM1")
        self.assertIsNone(forecasts[0].kalshi_market_id)
        self.assertNotIn("Kalshi", forecasts[0].market_view)

    def test_crypto_forecast_catalysts_do_not_use_sports_wording(self):
        report = _report("Bitcoin above 100k this week")

        forecasts = forecast.synthesize_forecasts(report)
        catalyst_text = " ".join(forecasts[0].upside_catalysts + forecasts[0].downside_catalysts).lower()

        self.assertIn("spot price", catalyst_text)
        for term in ("lineup", "injury", "rest", "tipoff"):
            self.assertNotIn(term, catalyst_text)


if __name__ == "__main__":
    unittest.main()
