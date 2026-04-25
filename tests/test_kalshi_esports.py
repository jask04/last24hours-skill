import unittest
from scripts.lib import kalshi, market_types

class KalshiEsportsTests(unittest.TestCase):
    def test_esports_topics_route_to_kalshi_series(self):
        self.assertIn("KXCS2GAME", kalshi._series_for_topic("CS2 matches today"))
        self.assertIn("KXVALGAME", kalshi._series_for_topic("Valorant games tonight"))
        self.assertIn("KXLOLGAME", kalshi._series_for_topic("LoL slate"))
        self.assertIn("KXESPORTS", kalshi._series_for_topic("eSports watchlist"))

    def test_kalshi_esports_market_classification(self):
        # Match outcome
        item = {
            "title": "NIP vs. BIG",
            "question": "Who will win NIP vs. BIG (Bo3)?",
            "url": "https://kalshi.com/markets/KXCS2GAME-26APR25-NIPBIG-NIP"
        }
        self.assertEqual(market_types.classify_market(item["title"], item["question"], item["url"]), "game_outcome")

        # Esports prop
        item_prop = {
            "title": "NIP vs. BIG: Map 1 Winner",
            "question": "Who will win Map 1 of NIP vs. BIG?",
            "url": "https://kalshi.com/markets/KXCS2GAME-26APR25-NIPBIG-M1NIP"
        }
        self.assertEqual(market_types.classify_market(item_prop["title"], item_prop["question"], item_prop["url"]), "esports_prop")

    def test_kalshi_live_board_includes_esports_series(self):
        series = kalshi._series_for_topic("Kalshi live markets")
        self.assertIn("KXCS2GAME", series)
        self.assertIn("KXVALGAME", series)
        self.assertIn("KXLOLGAME", series)

if __name__ == "__main__":
    unittest.main()
