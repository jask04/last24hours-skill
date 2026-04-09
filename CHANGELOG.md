# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Kalshi market discovery, normalization, scoring, rendering, and report serialization
- Forecast-first response contract across the skill, README, and extension metadata
- NBA slate expansion for broad queries such as `tomorrows nba games`, with matchup-level fan-out
- Slate forecast board rendering for broad NBA game queries

### Changed
- Prediction mode now defaults for forecastable topics including sports, weather, elections, macro, and event outcomes
- Prediction queries now prioritize Kalshi, Polymarket, X, Reddit, and relevant web above supporting social/video sources
- Compact rendering now frames output as forecast inputs and includes dedicated Kalshi sections
- Market ranking now weights liquidity, volume, open interest, and recent movement more heavily
- Broken localhost proxy environment variables are ignored automatically during HTTP requests
- Output writing now falls back cleanly when the default context-output directory is unavailable
- Reddit now uses free public search by default, with ScrapeCreators as optional enrichment
- Bluesky search now tries the public API path first and only falls back to authenticated search when needed

### Fixed
- Broad sports-slate runs now filter weak or irrelevant market matches more aggressively
- X matchup query extraction now preserves full team names such as `New York Knicks` and `Golden State Warriors`

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
