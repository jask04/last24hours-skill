# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `LAST24HOURS_DISABLE_SCRAPECREATORS` and `--no-scrapecreators` controls to skip ScrapeCreators-backed credit paths while keeping the key stored
- Kalshi market discovery, normalization, scoring, rendering, and report serialization
- Forecast-first response contract across the skill, README, and extension metadata
- NBA slate expansion for broad queries such as `tomorrows nba games`, with matchup-level fan-out
- Slate forecast board rendering for broad NBA game queries
- Market-anchored forecast synthesis objects for prediction queries, including blended Polymarket/Kalshi forecasts
- Sports evidence-quality heuristics that prefer injuries, lineups, rest, playoff context, and meaningful line movement
- Official no-key National Weather Service weather anchor for supported U.S. city aliases
- First-class weather report serialization via `WeatherItem` and `Report.weather`
- Shared domain evidence-quality helpers for sports, weather, macro, and NBA market filtering
- Topic-scoped `market_watchlist` query mode for prompts such as `NBA markets to watch today`, `best macro markets right now`, and `recommend Polymarket/Kalshi markets around Fed cuts`
- `MarketWatchItem` report serialization and compact rendering for ranked market picks with market signal, catalyst evidence, and risk notes
- One-shot market-watchlist ranker that scores Polymarket/Kalshi candidates by topic relevance, market depth, recent movement, catalyst evidence, and cross-market signal
- Shared market-signal fields for Polymarket, Kalshi, and market-watchlist report items, including implied probability, bid/ask, spread, midpoint, 24h movement, 24h volume, signal timestamp, signal quality, and missing-signal reason
- Kalshi batch candlestick enrichment for watchlist candidates, deriving 24h movement, 24h volume, latest open interest, and signal timestamps when public candle data is available
- Kalshi direct series/event expansion for NBA, Fed/rates, BTC, and ETH watchlist scans
- Market contract-type classification for game outcomes, player props, team props, futures, thresholds, macro binaries, and weather binaries
- Stdlib `unittest` regression harness for market typing, forecast/watchlist ranking, query classification, and report serialization
- Optional official Reddit OAuth backend using `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `LAST24HOURS_REDDIT_SOURCE`
- Deterministic forecast/search planner inspired by upstream `last30days` v3, with market-first source weights and bounded subquery expansion
- Cross-source evidence fusion for forecast explanations and market-watchlist catalysts, including light clustering and per-author caps

### Changed
- YouTube detection now accepts `yt-dlp` installed as a Python module, not just a `yt-dlp` executable on `PATH`
- Prediction mode now defaults for forecastable topics including sports, weather, elections, macro, and event outcomes
- Prediction queries now prioritize Kalshi, Polymarket, X, Reddit, and relevant web above supporting social/video sources
- Compact rendering now frames output as forecast inputs and includes dedicated Kalshi sections
- Market ranking now weights liquidity, volume, open interest, and recent movement more heavily
- Broken localhost proxy environment variables are ignored automatically during HTTP requests
- Output writing now falls back cleanly when the default context-output directory is unavailable
- Reddit now uses free public search by default, with ScrapeCreators as optional enrichment
- Bluesky search now tries the public API path first and only falls back to authenticated search when needed
- Broad NBA Reddit searches now suppress more incidental keyword matches from non-NBA communities, survey spam, and mirror-style sports subs
- Sports forecast explanations now stay market-led and drop more betting-bot, resale, and generic hype chatter
- Compact sports source sections now prefer higher-signal X and Reddit items instead of raw score-only ordering
- Weather and macro forecasts now suppress weak X, Reddit, and web evidence more aggressively and fall back to explicit market-driven or model-implied wording when signal is thin
- X query extraction now handles weather and macro prompts more cleanly, improving terms like `NYC rain tomorrow`, `Fed cut rates by June`, and `US recession in 2026`
- Supported U.S. weather prompts now prefer official NWS precipitation probability over social chatter when no clean market exists
- NBA slate compact output now league-locks raw Polymarket/Kalshi sections to NBA markets
- Weather and macro raw-section suppression now also applies to supporting social sections such as Bluesky and Truth Social
- No-market sports matchup forecasts now render with a neutral model-implied label instead of `Yes`
- NBA slate prompts now render an explicit no-direct-slate forecast fallback when only futures/awards markets are found
- Market-watchlist prompts now render `Market Picks To Watch` instead of a single forecast and keep rankings framed as informational market monitoring
- Watchlist mode keeps a wider market candidate pool than forecast mode before applying its own ranker
- Skill, README, and extension metadata now describe `/last24hours` as forecasting plus topic-scoped market-watchlist discovery
- Watchlist ranking now prioritizes measurable market signal quality, 24h volume, spread tightness, open interest/liquidity, and recent 24h repricing before catalyst context
- Watchlist risk notes now call out stale/near-certain prices, wide spreads, and missing enrichment instead of hiding weak market data behind generic market-signal wording
- Watchlist output now includes a near-cutoff Kalshi candidate for venue coverage when its score is close enough to the top-five cutoff
- Sports forecasts now require direct game-outcome markets before using a market as a matchup/slate anchor
- Watchlist output now labels props and threshold markets explicitly instead of presenting every item as a generic market pick
- Compact source-status rendering now uses ASCII-safe status labels for cleaner Windows/Codex output
- Reddit source selection now prefers official OAuth when configured, falls back to public JSON in `auto`, and reports Reddit OAuth/public JSON/ScrapeCreators separately
- Forecast and watchlist explanation selection now uses fused high-signal evidence while keeping Polymarket, Kalshi, and NWS as the probability anchors

### Fixed
- Broad sports-slate runs now filter weak or irrelevant market matches more aggressively
- X matchup query extraction now preserves full team names such as `New York Knicks` and `Golden State Warriors`
- Windows runs no longer show misleading `chmod 600` guidance for `.env` permission warnings
- NBA slate runs no longer leak cross-league city-name collisions such as MLB markets into NBA boards
- Polymarket macro multi-market rendering now falls back to clean `Yes` / `No` labels when question-derived labels would be malformed
- Market-watchlist phrasing such as `markets to watch` no longer misclassifies as a weather query
- Cross-market disagreement notes no longer compare adjacent contracts with different numeric thresholds as if they were the same market
- NBA slate forecasts no longer use player-prop contracts as game-outcome forecasts
- Report cache deserialization now round-trips Bluesky items
- Near-certain crypto threshold markets are suppressed from watchlists unless the unresolved movement/depth signal is strong enough
- Explicit `--search=bluesky` and `--search=bsky` runs no longer fall through to web-only mode
- Bluesky 403 errors now distinguish public search, auth-session, and authenticated-search failures without assuming app-password failure
- Disabled ScrapeCreators settings now gate the legacy ScrapeCreators X path in addition to Reddit, TikTok, and Instagram

## [1.0.0] - 2026-03-29

### Added
- Hour-based recency scoring (`recency_score_hours`) with 48h max window and <6h bonus zone
- Reweighted scoring: 40% recency, 30% relevance, 30% engagement
- Source tier rebalancing for 24h context (YouTube demoted, X/HN promoted)
- ASCII art banner and branding for last24hours
- Comprehensive README with installation, examples, and scoring explanation

### Changed
- Derived from [last30days](https://github.com/mvanhorn/last30days-skill) v2.9.5 (MIT)
- `--days` restricted to 1-2 (hard ceiling)
- Timeout profiles reduced ~65% (quick: 60s, default: 120s, deep: 200s)
- Cache TTL reduced to 12 hours for fresher results
- Default tiebreaker order prioritizes X and Reddit for real-time sources
- WebSearch weights shifted to 55% recency / 45% relevance

### Removed
- 30-day research scope and related defaults
