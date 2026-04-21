# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Refreshed README, skill instructions, and agent development guides to showcase current forecasting, watchlist, closing-soon, live-sports, paper-ledger, cleanup, and testing workflows
- Backfilled explicit release-discipline guidance after the published v1.0.17 -> v1.0.23 history jump so future work must ship as one versioned commit and push per patch release without silent gaps

## [1.0.28] - 2026-04-20

### Added
- `paper.py report` now emits a `current_skill_comparable_sample` rollup for resolved rows that are both current-version comparable and free of legacy noisy rationale text
- Open-paper diagnostics now break out version eras, legacy-noisy groups, source-health status rollups, and duplicate-cluster summaries so current post-hardening samples are easier to separate from older history

### Changed
- Duplicate-open-row diagnostics now distinguish legacy duplicate noise from current post-dedupe-era rows without rewriting any historical paper records

### Tested
- Added paper-ledger regressions for current-skill comparable rollups, legacy-noisy breakdowns, duplicate-era separation, and stored source-health status aggregation

## [1.0.27] - 2026-04-20

### Added
- Tech watchlist evidence matching now considers broader existing local text fields, including Reddit-derived insight text and relevance summaries, before deciding whether a catalyst snippet is truly entity-specific

### Fixed
- Long-dated tech threshold rows now drop out of the top set when enough stronger near-term company/model markets already exist
- Broad closing-soon watchlists now suppress weak low-actionability manual-rule rows instead of letting sparse soccer/curiosity markets survive by default
- Broad watchlist ranking keeps existing crypto/NBA-specific behavior intact while applying stronger actionability pressure to general scans

### Tested
- Added regressions for long-dated tech threshold suppression and broad closing-soon manual-rule row suppression

## [1.0.26] - 2026-04-20

### Added
- Source-health diagnostics now track degraded/error states for X and Web alongside the existing Reddit status model, with serialized bucket counts for sparse-source audit passes
- Degraded forecast debug counters now record macro-social and crypto-opinion suppression reasons so rendered diagnostics can explain why weak rows were hidden

### Fixed
- Degraded macro model-implied forecasts now only lead with non-social quality evidence by default; weak Fed pricing-color chatter falls back to the neutral macro explanation instead of becoming `why_line`
- Compact macro and crypto source sections now suppress weak X/Reddit chatter more aggressively so the rendered evidence no longer undercuts degraded fallback wording
- Compact X/Web sections and the source footer now distinguish `empty` from `degraded`/`error` states instead of presenting every failed source path as a simple zero-result run

### Tested
- Added regressions for degraded X/Web source-health serialization, macro social-pricing demotion, and compact crypto chatter suppression

## [1.0.25] - 2026-04-20

### Added
- New paper records now carry source-health diagnostics inside stored evidence payloads so later calibration can segment sparse-source and degraded-source runs

### Fixed
- Tech watchlists now reject generic tooling/directory chatter as catalyst evidence unless the text also carries real release, benchmark, leaderboard, eval, or ranking signal for the matched company or model
- Broad closing-soon watchlists now apply stronger settlement-quality pressure, so direct crypto reference-price and similarly cleaner-resolving rows can outrank odd manual-rule markets when the market signal is otherwise close
- Reddit evidence matching now considers enriched top-comment excerpts alongside comment insights, which broadens entity grounding without loosening the paper-safe filters

### Tested
- Added regressions for generic tech-tooling chatter rejection, broad closing-soon manual-rule demotion, and paper source-health payload carry-through

## [1.0.24] - 2026-04-20

### Added
- Source-health diagnostics now record blocked Reddit public-search attempts, degraded prediction-run counts by domain, and empty-source buckets for Reddit, X, and Web in serialized report JSON

### Fixed
- Reddit public JSON search now distinguishes blocked/degraded runs from true zero-result runs, and compact source status reports that difference explicitly
- Degraded macro forecasts now require cleaner non-social rationale leads by default, while strong official-style social macro context only leads when it clears a higher bar
- Degraded crypto and macro compact source sections now suppress thin promo or pricing-chatter rows more aggressively so the rendered evidence does not undercut the forecast rationale
- Broad closing-soon watchlists now delay duplicate-domain rows when a cleaner cross-domain top set is available, while crypto-only scans remain domain-pure

### Tested
- Added regressions for blocked Reddit source status, serialized source-health counters, and broad closing-soon cross-domain ranking behavior

## [1.0.23] - 2026-04-20

### Added
- Paper daily fixtures can now declare duplicate-suppression policy without a schema migration, and the shipped 10-topic paper portfolio defaults to skipping already-open duplicate market keys
- Open paper diagnostics now break out age buckets, duplicate clusters, and legacy noisy-rationale counts for audit passes

### Fixed
- Degraded macro and crypto forecasts now prefer official, market, and clean web/data context over thin social snippets, and model-implied fallbacks stay neutral when no clean evidence survives
- Tech watchlists now boost near-term company/model rows ahead of long-dated low-signal thresholds, while company-comparison catalysts stay entity-specific
- NBA watchlists now label scheduled ESPN rows as game status instead of live games, and paper bundle legs must be scheduled direct-game markets rather than already-live rows
- Adapter self-report text for Bird/X and YouTube now matches the current release version

### Tested
- Added regressions for degraded source reranking, tech actionability ranking, scheduled-vs-live ESPN labels, bundle scheduled-only gating, duplicate-skip behavior, open-paper diagnostics, and adapter version consistency

## [1.0.20] - 2026-04-20

### Added
- Daily paper portfolio entries can now declare `last24hours_args`, `pick_policy`, and `expected_pick_types` so one fixture can seed broader paper coverage without a second command path
- Expanded the default paper portfolio with recurring NBA watchlist, NBA paper-bundle, closing-soon, and crypto closing-soon calibration prompts

### Fixed
- Model-implied macro and crypto forecasts now reject more alert-spam, promo, betting, poll, and threshold-mismatched chatter before selecting `why_line` evidence
- Tech watchlists now require company/model-specific entity overlap, so Chinese AI rows no longer inherit Anthropic/Claude catalyst snippets
- Long-dated low-signal tech watchlist rows with zero volume are suppressed when stronger same-run rows already exist
- Open paper diagnostics now break out skill versions, pick types, domains, and repeated market keys so broader sampling is easier to audit

### Tested
- Added paper-ledger coverage for portfolio entry normalization, forwarded args, pick-policy filtering, expected-pick-type warnings, and duplicate open-row diagnostics
- Added forecast regressions for macro alert spam rejection, crypto promo rejection, and clean macro/crypto context acceptance
- Added watchlist regressions for company-specific tech catalyst matching and long-dated low-signal tech suppression

## [1.0.19] - 2026-04-20

### Fixed
- Sports forecast rationale now rejects generic sportsbook odds/betting copy even when it names the exact matchup and date
- Clean exact-date line-movement snippets remain eligible sports context when they avoid promotional or execution-style language
- Terminal progress messages now use probability/market-attention wording instead of betting-action phrasing
- Watchlist rendering now uses neutral `Market Watchlist` and `Outcome` labels instead of pick/action-adjacent wording

### Tested
- Added planner-fusion regressions for sportsbook-copy rejection and clean line-movement rationale eligibility

## [1.0.18] - 2026-04-20

### Fixed
- NBA paper bundle watchlists now only rank direct ESPN-matched game-outcome markets, excluding series, futures, totals, props, and unmatched game-looking markets from the surrounding watchlist as well as bundle construction
- Sports catalyst filtering now rejects ticket-availability chatter and promotional picks/bets posts while preserving clean exact-match injury, lineup, rest, playoff-incentive, and line-movement context
- Pregame ESPN context now omits placeholder 0-0 score, period 0, and 0.0 clock text while retaining live/final score and clock details

### Changed
- Paper bundle leg keys now use normalized unique NBA team tokens, and bundle legs require trusted ESPN matchup context before qualifying
- Paper ledger open-portfolio diagnostics now report paper-only bundle rows separately without counting them as missing automatic resolvers
- Bundle-intent progress and compact output now reuse paper-safe topic wording for user prompts that use parlay language

## [1.0.17] - 2026-04-20

### Added
- NBA date-window expansion for prompts such as `NBA games April 20 2026 through April 22 2026`, backed by ESPN public scoreboards
- Paper-only multi-leg bundle output for NBA game-outcome watchlists, with independence-baseline probability math, correlation warnings, and fragility notes
- `--paper-bundles` for recording the top paper bundle as metadata in the existing paper ledger without a schema migration

### Changed
- NBA game-outcome watchlist candidates can now carry ESPN score/status/start context outside closing-soon scans
- Bundle-intent prompts use product wording such as Paper Bundle and Multi-Leg Watchlist while retaining the existing low-signal picks/parlay chatter filters

## [1.0.16] - 2026-04-20

### Fixed
- Market-watchlist catalyst snippets now require market-specific entity and domain overlap, so broad closing-soon scans no longer attach unrelated promo posts to crypto, weather, or sports markets
- Low-signal promotional posts, giveaway/airdrop spam, signal-room pitches, and generic picks/parlay chatter are rejected as catalyst evidence
- Closing-soon output now falls back to market-signal-driven wording when no clean external catalyst clears the stricter filter

## [1.0.15] - 2026-04-19

### Changed
- Live-sports closing-soon scans now use ESPN team abbreviations, short names, full matchups, reversed matchups, and league-prefixed aliases when searching Polymarket
- Live-sports watchlists now return only direct matching game-outcome markets; series markets, futures, total-games props, player props, and wrong-matchup markets are rejected with diagnostics
- No-match live-sports output now distinguishes no live ESPN games from live games with no direct Polymarket game-outcome match
- Watchlist JSON and optional paper-watchlist notes now include live league, match confidence, and match reason for live sports candidates

## [1.0.14] - 2026-04-19

### Added
- Closing-soon market-watchlist mode for prompts such as `Polymarket markets closing soon`, with near-expiry Polymarket scanning, preserved close datetimes, minutes-to-close ranking, and settlement-rule warnings
- ESPN-backed live/starting-soon game detection for NBA, MLB, NHL, and NFL, used to search and label matching live sports Polymarket markets
- `--closing-window-hours`, `--live-sports`, and `--paper-watchlist` flags for narrowing scans, forcing live-game discovery, and recording selected watchlist candidates as paper-only picks

### Changed
- Market-watchlist output now surfaces close time, minutes to close, liquidity/spread context, live score/status when available, resolvability notes, and a warning to verify fast-moving lines in the Polymarket UI
- Optional paper-watchlist records store closing-soon reason, minutes to close, live-game context, and resolvability in `notes_json` without changing the SQLite schema

## [1.0.13] - 2026-04-19

### Fixed
- Sports forecast explanations now use a shared evidence-quality gate that rejects generic previews, ticket chatter, betting-bot posts, stale game threads, and historical clips as `Why this is the current line`
- Exact-date sportsbook odds and high-signal injury, lineup, rest, availability, and playoff-incentive reports remain eligible sports rationale
- Sports fallback wording now distinguishes market-backed forecasts from no-market model-implied forecasts when supporting evidence is thin

## [1.0.12] - 2026-04-19

### Fixed
- Date-specific sports forecasts now reject evidence snippets that explicitly mention a conflicting game date, preventing stale game threads from explaining later-game model-implied forecasts

## [1.0.11] - 2026-04-19

### Fixed
- Sports slate forecast explanations now apply matchup-side filtering to fused evidence drivers so one game's injury/status note cannot become another game's `Why this is the current line`

## [1.0.10] - 2026-04-19

### Added
- Auto-saved raw markdown reports can now be cleaned with `--clean-save-dir --save-dir DIR`, and normal `--save-dir` runs delete old `*-raw*.md` files after a configurable retention window
- `--as-of-date YYYY-MM-DD` and `LAST24HOURS_AS_OF_DATE` now make today/tomorrow resolution deterministic across date range, NBA slate, and weather paths

## [1.0.9] - 2026-04-19

### Fixed
- NBA slate detection now treats `NBA matchups tomorrow` as a slate query instead of falling back to a generic forecast
- Sports forecast anchoring now rejects stale same-team markets when the requested game date clearly conflicts with the market date

## [1.0.8] - 2026-04-19

### Added
- Paper ledger records now store the skill version on new runs and picks so future calibration can be compared across forecast-engine changes
- Paper reports now include open-portfolio diagnostics for favorite/balanced/longshot mix, model-implied picks, manual-resolution gaps, and legacy unversioned samples
- Market-watchlist paper extraction now prefers a balanced calibration sample when the top-ranked watchlist item is an extreme favorite

## [1.0.7] - 2026-04-19

### Added
- Model-implied forecasts now carry a visible degraded-run warning in JSON and compact output when no clean market or official anchor clears matching
- Paper-ledger calibration summaries now include favorite/longshot mix, average edge from 50%, and probability-bucket groups to make win-rate quality easier to audit
- Regression coverage for degraded forecast warning rendering and favorite-heavy paper portfolios

## [1.0.6] - 2026-04-19

### Fixed
- Crypto threshold forecasts now use the requested Yes side for compatible Yes/No threshold markets instead of blindly taking the highest-priced outcome
- Extreme near-term crypto threshold forecasts without a clean market now fall back to a lower model-implied range instead of a neutral 50/50-style estimate

## [1.0.5] - 2026-04-19

### Added
- Deterministic NBA paper-pick resolution through ESPN public scoreboard final results
- Deterministic NWS weather paper-pick resolution through observed station precipitation for completed forecast dates
- Regression tests for NBA winner/loser/open-game resolution and observed rain/no-rain/future-date weather resolution

## [1.0.4] - 2026-04-19

### Fixed
- Paper resolver now treats transient exchange/network exceptions as retryable and leaves affected market picks `open` instead of demoting them to `unknown`

## [1.0.3] - 2026-04-19

### Added
- Paper forecast ledger CLI at `scripts/paper.py` for hypothetical daily forecast tracking, later resolution, calibration reports, and conservative improvement suggestions
- Fixed paper portfolio fixture covering NBA slate, BTC threshold, Fed-rate, NYC rain, and AI coding-tools market-watchlist prompts
- SQLite paper ledger tables for daily runs and repeated paper picks without deduping repeated forecasts on the same market
- Best-effort Kalshi and Polymarket public resolution helpers plus manual resolution via `scripts/paper.py resolve --pick-id ID --outcome 1|0`
- macOS LaunchAgent installer for a daily 8:00 AM local paper runner with logs under `~/.local/share/last24hours/logs/`
- Regression tests for paper storage, extraction, resolution, calibration metrics, suggestion thresholds, and launchd plist generation

### Changed
- Version metadata is synchronized across the skill spec, README, Claude plugin manifest, Gemini extension manifest, and runtime source-status banner for the 1.0.3 patch batch
- Documentation now frames paper picks as hypothetical calibration records, not betting advice, trade execution, stake sizing, or automatic forecast-weight mutation

## [1.0.2] - 2026-04-19

### Added
- Last24hours-specific offline eval fixtures for NBA slate, BTC threshold, macro rates, NYC rain, and AI coding-tools market-watchlist prompts
- Version consistency tests covering the skill spec, README, Claude plugin manifest, Gemini extension manifest, and runtime source-status banner
- Targeted regression tests for eval fixture loading, HTTP query params and 429 retry caps, store update hardening, and Bluesky token cache refresh

### Changed
- `scripts/evaluate_search_quality.py` now loads default topics from `fixtures/eval_topics.json` and uses `origin/master` as the default baseline
- HTTP helpers now support stdlib query-param encoding, secret query-value redaction in debug logs, capped 429 attempts, and shared ScrapeCreators headers
- Bluesky authenticated fallback now refreshes cached session tokens after 90 minutes instead of reusing stale tokens

### Fixed
- Watchlist store update helpers now reject unknown dynamic SQL update fields before building update statements

## [1.0.1] - 2026-04-19

### Added
- Regression coverage for crypto threshold forecast anchoring, incompatible Polymarket/Kalshi blends, compatible threshold anchors, and crypto catalyst wording
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
- Version metadata is synchronized across the skill spec, README, Claude plugin manifest, Gemini extension manifest, and runtime source-status banner for the 1.0.1 patch batch
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
- Forecast anchoring now rejects numeric threshold contracts that answer a different outcome, such as treating `Bitcoin above 100k this week` as incompatible with lower BTC threshold or price-range markets
- Polymarket/Kalshi blending now requires threshold-compatible contracts instead of blending adjacent crypto thresholds or ranges
- Crypto and asset forecasts now use price, liquidity, ETF-flow, macro, and repricing catalysts instead of sports-only lineup, injury, rest, or tipoff language
- Broad sports-slate runs now filter weak or irrelevant market matches more aggressively
- Compact prediction output now suppresses raw Polymarket/Kalshi rows that were available but rejected by forecast-anchor matching
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
