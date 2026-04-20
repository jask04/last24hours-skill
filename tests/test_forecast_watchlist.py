import unittest
from unittest import mock

from scripts.lib import evidence_fusion, forecast, market_watchlist, render, schema


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
        self.assertLess(forecasts[0].forecast_probability, 0.20)
        self.assertIn("DEGRADED RUN WARNING", forecasts[0].degraded_warning)
        report.forecasts = forecasts
        self.assertIn("DEGRADED RUN WARNING", render.render_compact(report))

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
        self.assertEqual(forecasts[0].favorite_label, "Yes")
        self.assertAlmostEqual(forecasts[0].forecast_probability, 0.22)

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

    def test_broad_closing_soon_rejects_unrelated_stock_promo_catalyst(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin Up or Down - April 20, 4AM ET",
                question="Bitcoin Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/bitcoin-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.30), ("Down", 0.70)],
                engagement=_engagement(volume=24_000, liquidity=6_000),
                market_type="crypto_daily",
                market_signal_quality=0.79,
                volume_24h=24_000,
                best_bid=0.29,
                best_ask=0.30,
                spread=0.01,
                movement_24h=-21.0,
                relevance=0.95,
                minutes_to_close=17,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Big thanks to @PriyRaval - stocks are on a tear! He drops daily winners that rise super fast. You need this in your feed. #StockMarket #Inflation",
                url="https://x.com/example/status/1",
                author_handle="promo",
                score=95,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertEqual(items[0].evidence_refs, [])
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)

    def test_crypto_market_specific_catalyst_is_accepted(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Ethereum Up or Down - April 20, 4AM ET",
                question="Ethereum Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/ethereum-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.22), ("Down", 0.78)],
                engagement=_engagement(volume=50_000, liquidity=25_000),
                market_type="crypto_daily",
                market_signal_quality=0.80,
                volume_24h=50_000,
                best_bid=0.22,
                best_ask=0.23,
                spread=0.01,
                movement_24h=-18.0,
                relevance=0.95,
                minutes_to_close=15,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Ethereum volatility jumps as ETF flow data and liquidation pressure hit ETH price support before the daily close.",
                url="https://x.com/example/status/2",
                author_handle="crypto",
                score=92,
            )
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("Ethereum volatility", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)
        self.assertEqual(items[0].evidence_refs, ["X1 https://x.com/example/status/2"])

    def test_soccer_watchlist_rejects_unrelated_promo_and_requires_match_overlap(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="FK Oleksandriya vs. RNK Veres Rivne",
                question="Will FK Oleksandriya win on 2026-04-20?",
                url="https://polymarket.com/event/ukr1-ole-ver-2026-04-20",
                outcome_prices=[("FK Oleksandriya", 0.32), ("RNK Veres Rivne", 0.38)],
                engagement=_engagement(volume=10_000, liquidity=10_000),
                market_type="game_outcome",
                market_signal_quality=0.45,
                volume_24h=10_000,
                relevance=0.9,
                minutes_to_close=77,
                closing_soon_reason="closing_soon",
            )
        ]
        report.x = [
            schema.XItem(
                id="X1",
                text="Daily winners are on fire and my VIP picks keep cashing.",
                url="https://x.com/example/status/3",
                author_handle="promo",
                score=99,
            ),
            schema.XItem(
                id="X2",
                text="FK Oleksandriya vs RNK Veres Rivne is delayed by heavy rain with the live score still 0-0.",
                url="https://x.com/example/status/4",
                author_handle="matchreport",
                score=80,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("FK Oleksandriya", items[0].catalyst_summary)
        self.assertNotIn("Daily winners", items[0].catalyst_summary)
        self.assertIn("fresh catalyst context", items[0].why_ranks)

    def test_weather_market_requires_location_specific_forecast_evidence(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Highest temperature in Shanghai on April 20?",
                question="Will the highest temperature in Shanghai be 18C on April 20?",
                url="https://polymarket.com/event/highest-temperature-in-shanghai-on-april-20-2026",
                outcome_prices=[("Yes", 0.86), ("No", 0.14)],
                engagement=_engagement(volume=100_000, liquidity=50_000),
                market_type="weather_binary",
                market_signal_quality=0.70,
                volume_24h=100_000,
                best_bid=0.86,
                best_ask=0.87,
                spread=0.01,
                relevance=0.95,
                minutes_to_close=120,
                closing_soon_reason="closing_soon",
            )
        ]
        report.web = [
            schema.WebSearchItem(
                id="W1",
                title="Beijing weather update",
                url="https://example.com/beijing",
                source_domain="example.com",
                snippet="The forecast model shows warmer temperatures and rain chances in Beijing.",
                score=90,
            ),
            schema.WebSearchItem(
                id="W2",
                title="Shanghai weather forecast",
                url="https://example.com/shanghai",
                source_domain="example.com",
                snippet="Shanghai forecast models show the highest temperature near 18C today.",
                score=80,
            ),
        ]

        items = market_watchlist.synthesize_market_watchlist(report)

        self.assertIn("Shanghai weather forecast", items[0].catalyst_summary)
        self.assertNotIn("Beijing", items[0].catalyst_summary)

    def test_fused_watchlist_driver_uses_same_market_specific_filter(self):
        report = _report("Polymarket markets closing soon")
        report.planning_notes = ["closing_soon"]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Bitcoin Up or Down - April 20, 4AM ET",
                question="Bitcoin Up or Down - April 20, 4AM ET",
                url="https://polymarket.com/event/bitcoin-up-or-down-april-20-2026-4am-et",
                outcome_prices=[("Up", 0.30), ("Down", 0.70)],
                engagement=_engagement(volume=24_000, liquidity=6_000),
                market_type="crypto_daily",
                market_signal_quality=0.79,
                volume_24h=24_000,
                spread=0.01,
                relevance=0.95,
                minutes_to_close=17,
                closing_soon_reason="closing_soon",
            )
        ]
        fused = evidence_fusion.FusionResult(
            drivers=[
                evidence_fusion.FusedEvidence(
                    text="Inflation is moving markets, and these daily stock winners are on a tear.",
                    source="x",
                    source_item_id="X1",
                    author_key="x:promo",
                    cluster_key="inflation markets",
                    score=0.95,
                )
            ],
            candidate_count=1,
            cluster_count=1,
        )

        with mock.patch("scripts.lib.market_watchlist.evidence_fusion.fuse_evidence", return_value=fused):
            items = market_watchlist.synthesize_market_watchlist(report)

        self.assertEqual(items[0].catalyst_summary, "Catalyst context is thin; ranking is mostly market-signal driven.")
        self.assertNotIn("fresh catalyst context", items[0].why_ranks)


if __name__ == "__main__":
    unittest.main()
