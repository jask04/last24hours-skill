"""Regression coverage for eSports subdomain routing (CS2, Valorant, LoL)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.lib import evidence_quality as eq  # noqa: E402
from scripts import paper  # noqa: E402


class EsportsSubdomainTests(unittest.TestCase):
    def test_cs2_market_text_detection(self):
        self.assertTrue(eq.is_cs2_market_text("Counter-Strike 2: NAVI vs FaZe"))
        self.assertTrue(eq.is_cs2_market_text("cs2 match winner"))
        self.assertFalse(eq.is_cs2_market_text("Valorant VCT match"))
        self.assertFalse(eq.is_cs2_market_text("League of Legends LEC final"))

    def test_valorant_market_text_detection(self):
        self.assertTrue(eq.is_valorant_market_text("Valorant Champions Tour final"))
        self.assertTrue(eq.is_valorant_market_text("VCT Americas Sentinels vs LOUD"))
        self.assertFalse(eq.is_valorant_market_text("Counter-Strike 2 NAVI vs FaZe"))
        self.assertFalse(eq.is_valorant_market_text("LEC Spring Finals"))

    def test_lol_market_text_detection(self):
        self.assertTrue(eq.is_lol_market_text("League of Legends Worlds final"))
        self.assertTrue(eq.is_lol_market_text("LEC Spring Split final"))
        self.assertTrue(eq.is_lol_market_text("LCK T1 vs Gen.G"))
        self.assertTrue(eq.is_lol_market_text("lol esports match"))
        self.assertFalse(eq.is_lol_market_text("random meme post lol that was funny"))
        self.assertFalse(eq.is_lol_market_text("Valorant VCT match"))

    def test_esports_subdomain_of_returns_specific_labels(self):
        self.assertEqual(eq.esports_subdomain_of("Counter-Strike 2 matches today"), "cs2")
        self.assertEqual(eq.esports_subdomain_of("Valorant matches today"), "valorant")
        self.assertEqual(eq.esports_subdomain_of("League of Legends matches today"), "lol")
        self.assertEqual(eq.esports_subdomain_of("esports markets to watch today"), "")

    def test_paper_subdomain_routes_valorant_and_lol(self):
        self.assertEqual(paper._subdomain("Valorant matches today"), "valorant")
        self.assertEqual(paper._subdomain("League of Legends matches today"), "lol")
        self.assertEqual(paper._subdomain("Counter-Strike 2 matches today"), "cs2")
        self.assertEqual(paper._subdomain("esports markets to watch today"), "")

    def test_subdomain_cross_title_mismatch_is_rejected(self):
        # Valorant prompt should not accept a CS2 title (and vice-versa)
        self.assertNotEqual(
            eq.esports_subdomain_of("Valorant matches today"),
            eq.esports_subdomain_of("Counter-Strike 2: NAVI vs FaZe"),
        )
        self.assertNotEqual(
            eq.esports_subdomain_of("League of Legends matches today"),
            eq.esports_subdomain_of("Valorant VCT final"),
        )


if __name__ == "__main__":
    unittest.main()
