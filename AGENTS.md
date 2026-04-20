# last24hours - Development Guide

## Overview

Real-time forecasting and market-watchlist skill for Codex. It defaults to probability-first answers using Polymarket, Kalshi, X, Reddit, Hacker News, official National Weather Service data, and the web, with strongest support for prediction markets, sports, weather, elections, macro, and event outcomes.

Current major workflows:
- probability forecasts anchored to Polymarket/Kalshi/NWS when clean anchors exist
- NBA slate expansion for prompts such as `tomorrows nba games`
- topic-scoped market watchlists for prompts such as `NBA markets to watch today`
- Polymarket closing-soon scans for prompts such as `Polymarket markets closing soon`
- ESPN-backed live/starting-soon sports watchlists for NBA, MLB, NHL, and NFL
- paper-only forecast ledger and daily macOS runner through `scripts/paper.py`
- disposable raw markdown report cleanup through `--save-dir`, `--save-retention-days`, and `--clean-save-dir`

Derived from [last30days](https://github.com/mvanhorn/last30days-skill) v2.9.5 (MIT licensed).

## Running Locally

```bash
# Basic query
python3 scripts/last24hours.py "topic" --quick

# Diagnose source availability
python3 scripts/last24hours.py --diagnose

# Compact output
python3 scripts/last24hours.py "topic" --quick --emit=compact

# Closing-soon and live sports scans
python3 scripts/last24hours.py "Polymarket markets closing soon" --quick --emit=compact --closing-window-hours 6
python3 scripts/last24hours.py "live sports games on Polymarket right now" --quick --emit=compact --search=polymarket

# Deterministic relative-date testing
python3 scripts/last24hours.py "NBA matchups tomorrow" --quick --emit=compact --as-of-date 2026-04-19

# Paper ledger
python3 scripts/paper.py daily --portfolio fixtures/paper_portfolio.json --quick --dry-run
python3 scripts/paper.py resolve
python3 scripts/paper.py report --days 30
```

## Configuration

API keys live in `~/.config/last24hours/.env`. Copy from `.env.example` or create manually.

Minimum useful setup: X cookies (`AUTH_TOKEN`, `CT0`) for X search.

Reddit public JSON search works without paid scraper credentials. Optional official Reddit OAuth credentials improve the free Reddit path when available. `SCRAPECREATORS_API_KEY` is optional and improves paid Reddit comment enrichment plus TikTok/Instagram coverage; `LAST24HOURS_DISABLE_SCRAPECREATORS=1` skips credit-backed paths while keeping the key stored.

Polymarket and Kalshi public market discovery require no auth. NWS weather lookup requires no auth for supported U.S. aliases.

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
- Date-specific sports forecasts reject stale same-team markets when the market date conflicts with the requested game date
- Sports rationale prefers injury, availability, lineup, rest, playoff incentives, and exact-date line movement over generic previews, ticket posts, betting bots, historical clips, and stale game threads

### Market Watchlists
- Query classification routes `markets to watch`, `closing soon`, `live markets`, `live games`, `settling soon`, and similar prompts to `market_watchlist`
- Closing-soon scans use Polymarket public-search, preserve close datetimes, compute minutes-to-close, and filter expired/closed/no-liquidity/effectively settled markets
- Live-sports watchlists only surface direct matching game-outcome markets; series/futures/totals/props/wrong-matchup markets are rejected
- Catalyst snippets must match the candidate market domain and entity; generic promo posts, signal-room pitches, picks/parlay chatter, giveaway spam, and domain-mismatched snippets are rejected

### Paper Ledger
- `scripts/paper.py daily` runs the fixed fixture portfolio and records hypothetical picks under `~/.local/share/last24hours/paper/`
- `resolve`, `report`, and `suggest` update calibration, report Brier/log-loss metrics, and print conservative improvement suggestions
- The ledger is paper-only: no trade execution, stake sizing, bankroll advice, or automatic forecast-weight mutation

## Testing

```bash
# Regression tests
python3 -m unittest discover -s tests
python3 -m compileall -q scripts tests
git diff --check

# Check for stale last30days references
grep -r "last30\|30 days\|days.*30" scripts/

# Live tests
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "Polymarket markets closing soon" --quick --emit=compact --closing-window-hours 6
python3 scripts/last24hours.py "live sports games on Polymarket right now" --quick --emit=compact --search=polymarket
```

## Git Conventions

- Never include Codex as author or co-author in commits
- Work on the current branch by default; do not create `codex/*` branches
- Push incremental commits frequently so the repo history stays current
- Keep commits focused and descriptive
