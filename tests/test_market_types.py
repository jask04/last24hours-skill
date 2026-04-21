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

    def test_sports_slug_with_abbreviated_matchup_classifies_as_game_outcome(self):
        self.assertEqual(
            market_types.classify_market(
                "LAL vs HOU",
                "LAL vs HOU",
                "https://polymarket.com/event/nba-lal-hou-2026-04-21",
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

    def test_kalshi_nba_winner_contract_classifies_as_game_outcome(self):
        self.assertEqual(
            market_types.classify_market(
                "Game 3: New York at Atlanta",
                "Game 3: New York at Atlanta Winner?",
                "https://api.elections.kalshi.com/trade-api/v2/markets/KXNBAGAME-26APR23NYKATL-NYK",
            ),
            "game_outcome",
        )

    def test_kalshi_nba_series_winner_contract_classifies_as_futures(self):
        self.assertEqual(
            market_types.classify_market(
                "Eastern Conference First Round",
                "Knicks vs Hawks Series Winner?",
                "https://api.elections.kalshi.com/trade-api/v2/markets/KXNBASERIES-26APR-NYKATL-NYK",
            ),
            "futures",
        )

    def test_kalshi_fed_decision_contract_classifies_as_macro_binary(self):
        self.assertEqual(
            market_types.classify_market(
                "Fed decision in Jun 2026?",
                "Will the Federal Reserve Cut rates by 25bps at their June 2026 meeting?",
                "https://api.elections.kalshi.com/trade-api/v2/markets/KXFEDDECISION-26JUN-C25",
            ),
            "macro_binary",
        )

    def test_kalshi_fed_rate_threshold_contract_classifies_as_macro_binary(self):
        self.assertEqual(
            market_types.classify_market(
                "Fed funds rate after Jun 2026 meeting?",
                "Will the upper bound of the federal funds rate be above 4.25% following the Fed's Jun 17, 2026 meeting?",
                "https://api.elections.kalshi.com/trade-api/v2/markets/KXFED-26JUN-T4.25",
            ),
            "macro_binary",
        )

    def test_crypto_up_or_down_classifies_as_crypto_daily(self):
        self.assertEqual(
            market_types.classify_market(
                "Bitcoin Up or Down - April 20, 12AM ET",
                "Bitcoin Up or Down - April 20, 12AM ET",
                "https://polymarket.com/event/bitcoin-up-or-down-april-20-2026-12am-et",
            ),
            "crypto_daily",
        )


if __name__ == "__main__":
    unittest.main()
