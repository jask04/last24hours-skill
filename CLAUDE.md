# last24hours — Development Guide

## Overview

Real-time research skill for Claude Code. Searches Reddit, X, Hacker News, YouTube, TikTok, Bluesky, Polymarket, and the web for content from the **last 24-48 hours**.

Derived from [last30days](https://github.com/mvanhorn/last30days-skill) v2.9.5 (MIT licensed).

## Running Locally

```bash
# Basic query
python3 scripts/last24hours.py "topic" --quick

# Diagnose source availability
python3 scripts/last24hours.py --diagnose

# Compact output
python3 scripts/last24hours.py "topic" --quick --emit=compact
```

## Configuration

API keys live in `~/.config/last24hours/.env`. Copy from `.env.example` or create manually.

Minimum useful setup: `SCRAPECREATORS_API_KEY` (Reddit/TikTok/Instagram) + X cookies (`AUTH_TOKEN`, `CT0`).

## Architecture

### Scoring (scripts/lib/score.py)
- **40% recency** (hour-based, not day-based) / 30% relevance / 30% engagement
- `recency_score_hours()` in `scripts/lib/dates.py` — 48h max, <6h items get 90+ bonus

### Source Tiers (scripts/lib/query_type.py)
- Query type detection → source tier selection (tier1=always, tier2=if available, tier3=opt-in)
- YouTube is tier2 in most categories (videos rarely appear within 24h)
- X and HN are tier1 for breaking_news

### Timeouts
- Quick: 60s, Default: 120s, Deep: 200s (reduced ~65% from last30days)

## Testing

```bash
# Syntax check
python3 -c "import py_compile; py_compile.compile('scripts/last24hours.py', doraise=True)"

# Check for stale last30days references
grep -r "last30\|30 days\|days.*30" scripts/

# Live test
python3 scripts/last24hours.py "NBA playoffs" --quick --emit=compact
```

## Git Conventions

- Never include Claude as author or co-author in commits
- Keep commits focused and descriptive
