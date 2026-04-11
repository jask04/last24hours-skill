import unittest

from scripts.lib import market_types


class MarketTypeTests(unittest.TestCase):
    def test_nba_player_prop_classifies_as_player_prop(self):
        self.assertEqual(
            market_types.classify_market(
                "Thunder vs. Nuggets",
                "Christian Braun: Assists O/U 0.5",
                "https://polymarket.com/event/nba-okc-den-2026-04-10",
            ),
            "player_prop",
        )

    def test_nba_matchup_classifies_as_game_outcome(self):
        self.assertEqual(
            market_types.classify_market(
                "Lakers vs. Warriors",
                "Lakers vs. Warriors winner",
                "https://polymarket.com/event/nba-lal-gsw-2026-04-12",
            ),
            "game_outcome",
        )

    def test_crypto_threshold_classifies_as_threshold(self):
        self.assertEqual(
            market_types.classify_market(
                "Bitcoin above ___ on April 11?",
                "Will the price of Bitcoin be above $64,000 on April 11?",
                "https://polymarket.com/event/bitcoin-above-on-april-11",
            ),
            "threshold",
        )

    def test_price_band_market_classifies_as_threshold(self):
        self.assertEqual(
            market_types.classify_market(
                "Ethereum price on April 11?",
                "Will the price of Ethereum be between $1,600 and $1,700 on April 11?",
                "https://polymarket.com/event/ethereum-price-on-april-11",
            ),
            "threshold",
        )

    def test_time_at_does_not_make_crypto_price_range_a_game_outcome(self):
        self.assertEqual(
            market_types.classify_market(
                "Bitcoin price range on Apr 17, 2026 at 5pm EDT?",
                "Bitcoin price range on Apr 17, 2026?",
                "https://api.elections.kalshi.com/trade-api/v2/markets/KXBTC-26APR1717-B72250",
            ),
            "threshold",
        )


if __name__ == "__main__":
    unittest.main()
