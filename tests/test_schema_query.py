import unittest
from unittest import mock

from scripts.lib import env, query_type, schema, youtube_yt


class SchemaQueryTests(unittest.TestCase):
    def test_query_type_regressions(self):
        self.assertEqual(query_type.detect_query_type("markets to watch"), "market_watchlist")
        self.assertEqual(query_type.detect_query_type("tornado watch in NYC"), "prediction")

    def test_report_round_trips_bluesky_and_market_signal_fields(self):
        report = schema.Report(
            topic="NYC rain tomorrow",
            range_from="2026-04-10",
            range_to="2026-04-11",
            generated_at="2026-04-11T00:00:00+00:00",
            mode="both",
        )
        report.bluesky = [
            schema.BlueskyItem(
                id="BS1",
                text="Forecast model update",
                url="https://bsky.app/profile/example/post/1",
                author_handle="example.bsky.social",
                display_name="Example",
                score=42,
            )
        ]
        report.weather = [
            schema.WeatherItem(
                id="WX1",
                title="New York, NY rain",
                location="New York, NY",
                forecast_date="2026-04-12",
                url="https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly",
                probability=0.06,
                probability_pct=6,
            )
        ]
        report.polymarket = [
            schema.PolymarketItem(
                id="PM1",
                title="Fed Decision in June?",
                question="Will the Fed decrease interest rates by 50+ bps after the June 2026 meeting?",
                url="https://polymarket.com/event/fed-decision-in-june-825",
                outcome_prices=[("Yes", 0.01), ("No", 0.99)],
                implied_probability=0.99,
                best_bid=0.98,
                best_ask=0.99,
                spread=0.01,
                midpoint=0.985,
                movement_24h=-1.0,
                volume_24h=250_000,
                market_signal_quality=0.7,
                signal_timestamp="2026-04-11T00:00:00Z",
                signal_missing_reason="",
                market_type="macro_binary",
            )
        ]
        report.kalshi = [
            schema.KalshiItem(
                id="KA1",
                title="Fed rates",
                question="Will rates decrease in June?",
                url="https://api.elections.kalshi.com/trade-api/v2/markets/KX",
                ticker="KX",
                current_probability=0.12,
                market_type="macro_binary",
                movement_24h=2.0,
                volume_24h=10_000,
                market_signal_quality=0.5,
            )
        ]
        report.forecasts = [
            schema.ForecastItem(
                title="Fed rates",
                forecast_probability=0.12,
                anchor_source="kalshi",
                confidence_level="moderate-low",
            )
        ]
        report.market_watchlist = [
            schema.MarketWatchItem(
                id="MW1",
                title="Fed rates",
                question="Will rates decrease in June?",
                venue="Kalshi",
                url="https://kalshi.com",
                market_type="macro_binary",
                market_signal_quality=0.5,
                movement_24h=2.0,
            )
        ]

        restored = schema.Report.from_dict(report.to_dict())

        self.assertEqual(restored.bluesky[0].id, "BS1")
        self.assertEqual(restored.weather[0].probability_pct, 6)
        self.assertEqual(restored.polymarket[0].market_type, "macro_binary")
        self.assertEqual(restored.polymarket[0].spread, 0.01)
        self.assertEqual(restored.kalshi[0].market_type, "macro_binary")
        self.assertEqual(restored.forecasts[0].anchor_source, "kalshi")
        self.assertEqual(restored.market_watchlist[0].market_type, "macro_binary")

    def test_scrapecreators_disable_flag_preserves_free_paths(self):
        config = {
            "SCRAPECREATORS_API_KEY": "sc-key",
            "APIFY_API_TOKEN": None,
            "LAST24HOURS_DISABLE_SCRAPECREATORS": "1",
        }

        self.assertTrue(env.scrapecreators_disabled(config))
        self.assertFalse(env.is_instagram_available(config))
        self.assertEqual(env.get_instagram_token(config), "")
        self.assertFalse(env.is_tiktok_available(config))
        self.assertEqual(env.get_tiktok_token(config), "")
        self.assertEqual(env.get_reddit_source(config), "public")

    def test_ytdlp_module_fallback_counts_as_available(self):
        with mock.patch("scripts.lib.youtube_yt.shutil.which", return_value=None), \
             mock.patch("scripts.lib.youtube_yt.importlib.util.find_spec", return_value=object()):
            self.assertTrue(youtube_yt.is_ytdlp_installed())
            self.assertEqual(youtube_yt._ytdlp_command()[:2], [youtube_yt.sys.executable, "-m"])


if __name__ == "__main__":
    unittest.main()
