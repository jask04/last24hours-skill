"""Static casino-game reference table for /last24hours v1.0.54.

Online-casino line data is either proprietary (book-specific odds boosts),
state-regulated monthly disclosures (NJ DGE RTP reports — monthly PDFs, not
real-time), or unpublished (slot RTPs buried behind license agreements).
Live scraping is not a viable path.

For v1.0.54 we ship a conservative static reference table of house edges for
the four most commonly-queried casino games. The skill can cite these numbers
as context when a user asks about casino markets ("what's the house edge on
American roulette?") without pretending to track live book odds.

The numbers are the textbook values for standard rule sets. Real-world edges
vary by exact rule variant (number of decks, whether dealer hits soft 17,
whether surrender is offered, etc.) — the per-game `notes` field flags the
rule assumptions so surfaced context is honest about them.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# House edge = expected loss per unit wagered, as a fraction (0.005 = 0.5%).
# Sources: Wizard of Odds reference tables, textbook probability derivations
# (American roulette 2/38 = 5.26%, European roulette 1/37 = 2.70%, etc.).
CASINO_REFERENCE: Dict[str, Dict[str, Any]] = {
    "blackjack": {
        "game": "Blackjack",
        "category": "table",
        "house_edge": 0.005,
        "edge_range": (0.004, 0.02),
        "notes": (
            "Assumes basic-strategy play on a 6-deck, dealer-stands-on-soft-17, "
            "double-after-split, no-surrender table. Edge rises sharply against "
            "non-basic-strategy play or tighter rules (H17, 8-deck, no-DAS)."
        ),
        "rtp": 0.995,
    },
    "roulette_european": {
        "game": "European Roulette",
        "category": "table",
        "house_edge": 0.027,
        "edge_range": (0.027, 0.027),
        "notes": "Single-zero wheel. Edge is exactly 1/37 on every standard bet.",
        "rtp": 0.973,
    },
    "roulette_american": {
        "game": "American Roulette",
        "category": "table",
        "house_edge": 0.0526,
        "edge_range": (0.0526, 0.0789),
        "notes": (
            "Double-zero wheel. Edge is 2/38 on every bet except the five-number "
            "(0-00-1-2-3) basket bet at 7.89%."
        ),
        "rtp": 0.9474,
    },
    "craps_pass_line": {
        "game": "Craps (pass line, no odds)",
        "category": "table",
        "house_edge": 0.0141,
        "edge_range": (0.0014, 0.0141),
        "notes": (
            "Flat pass-line bet. Taking 3x/4x/5x free odds drops effective edge "
            "on total wagered to ~0.37%; 10x odds drops it to ~0.18%."
        ),
        "rtp": 0.9859,
    },
    "baccarat_banker": {
        "game": "Baccarat (banker bet)",
        "category": "table",
        "house_edge": 0.0106,
        "edge_range": (0.0106, 0.0124),
        "notes": (
            "Banker bet after 5% commission. Player bet runs 1.24%; Tie bet "
            "(8:1) runs 14.36% and should be avoided."
        ),
        "rtp": 0.9894,
    },
    "video_poker_jacks_or_better": {
        "game": "Video Poker (9/6 Jacks or Better)",
        "category": "machine",
        "house_edge": 0.0046,
        "edge_range": (0.0046, 0.05),
        "notes": (
            "Full-pay 9/6 schedule with optimal strategy. Pay tables vary by "
            "machine; 8/5 drops RTP by ~2.3 percentage points."
        ),
        "rtp": 0.9954,
    },
    "slots_typical": {
        "game": "Slots (typical Vegas Strip)",
        "category": "machine",
        "house_edge": 0.08,
        "edge_range": (0.02, 0.15),
        "notes": (
            "Individual slot RTPs are usually not published. Regulated-market "
            "aggregate reports (NJ DGE, NV Gaming Control) put Strip-style slot "
            "floors at roughly 90-92% RTP."
        ),
        "rtp": 0.92,
    },
}

# Keyword → reference-key lookup. Order matters: longer / more-specific
# keywords are checked first so "american roulette" beats plain "roulette".
_KEYWORD_MAP: List[tuple] = [
    (re.compile(r"\bamerican roulette\b", re.I), "roulette_american"),
    (re.compile(r"\beuropean roulette\b|\bsingle[-\s]?zero roulette\b", re.I), "roulette_european"),
    (re.compile(r"\bdouble[-\s]?zero roulette\b", re.I), "roulette_american"),
    (re.compile(r"\broulette\b", re.I), "roulette_american"),  # default to American
    (re.compile(r"\bvideo poker\b|\bjacks or better\b|\b9/6\b", re.I), "video_poker_jacks_or_better"),
    (re.compile(r"\bbaccarat\b|\bpunto banco\b", re.I), "baccarat_banker"),
    (re.compile(r"\bcraps\b|\bpass line\b", re.I), "craps_pass_line"),
    (re.compile(r"\bblackjack\b|\b21\b(?!\s*(?:savage|pilots|jump))", re.I), "blackjack"),
    (re.compile(r"\bslots?\b|\bslot machines?\b", re.I), "slots_typical"),
]


def lookup_casino_context(topic: str) -> List[Dict[str, Any]]:
    """Return the casino reference rows matching the topic (zero or more)."""
    if not topic:
        return []
    matched: List[str] = []
    seen = set()
    for pattern, key in _KEYWORD_MAP:
        if pattern.search(topic) and key not in seen:
            matched.append(key)
            seen.add(key)
    return [build_reference_item(key, topic=topic) for key in matched]


def build_reference_item(key: str, *, topic: str = "") -> Dict[str, Any]:
    """Return a normalized casino reference item for a given key."""
    entry = CASINO_REFERENCE.get(key)
    if not entry:
        return {}
    return {
        "kind": "casino_reference",
        "key": key,
        "game": entry["game"],
        "category": entry["category"],
        "house_edge": entry["house_edge"],
        "edge_range": list(entry.get("edge_range", (entry["house_edge"], entry["house_edge"]))),
        "rtp": entry.get("rtp"),
        "notes": entry.get("notes", ""),
        "topic": topic,
    }


def is_casino_query(topic: str) -> bool:
    """Quick check: does the topic look like it's asking about casino games?"""
    return bool(lookup_casino_context(topic))


def available_keys() -> List[str]:
    """Return all reference keys (stable for diagnostics)."""
    return sorted(CASINO_REFERENCE.keys())
