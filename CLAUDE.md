# last24hours - Development Guide

## Overview

Real-time forecasting skill for Codex, Claude Code, and Gemini. It defaults to prediction-mode answers and searches the last 24-48 hours across Polymarket, Kalshi, X, Reddit, Hacker News, YouTube, TikTok, Bluesky, and the web.

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

Minimum useful setup: X cookies (`AUTH_TOKEN`, `CT0`) for X search.

Reddit public JSON search works without paid scraper credentials. Optional official Reddit OAuth credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`) improve the free Reddit path when available. `LAST24HOURS_REDDIT_SOURCE=auto|oauth|public` controls whether the skill prefers OAuth, forces OAuth-first fallback warnings, or forces public JSON.

`SCRAPECREATORS_API_KEY` is optional and improves paid Reddit enrichment plus TikTok/Instagram coverage; keep `LAST24HOURS_DISABLE_SCRAPECREATORS=1` set when credits are exhausted.

No auth is required for Polymarket or Kalshi public market discovery.

## Architecture

### Scoring (`scripts/lib/score.py`)
- 40% recency (hour-based, not day-based) / 30% relevance / 30% engagement for general recency scoring
- Prediction mode further boosts market quality, price movement, and liquidity/open-interest signals
- `recency_score_hours()` in `scripts/lib/dates.py` uses a 48h max window, with a strong boost under 6h

### Source Tiers (`scripts/lib/query_type.py`)
- Query type detection maps forecastable topics into `prediction` by default
- Prediction tier prioritizes Kalshi, Polymarket, X, Reddit, and relevant web
- YouTube, TikTok, Instagram, Bluesky, and Truth Social are supporting sources unless explicitly requested

### Sports Slate Expansion
- Broad NBA slate queries such as `tomorrows nba games` expand into matchup-specific searches
- X, Polymarket, and Kalshi fan out per scheduled game instead of treating the whole slate as one generic topic

### Timeouts
- Quick: 60s, Default: 120s, Deep: 200s

## Testing

```bash
# Syntax check
python3 -c "import py_compile; py_compile.compile('scripts/last24hours.py', doraise=True)"

# Check for stale last30days references
grep -r "last30\|30 days\|days.*30" scripts/

# Live tests
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact
```

## Git Conventions

- Never include Claude or Codex as author or co-author in commits
- Keep commits focused and descriptive
