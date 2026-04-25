# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.0.80] - 2026-04-25

### Added
- `scripts/lib/kalshi.py`: Added Kalshi eSports support with specific series routing for `KXCS2GAME`, `KXVALGAME`, and `KXLOLGAME`.
- `scripts/lib/kalshi.py`: Added generic `esports` league detection and series mapping to improve discovery for broad eSports prompts.
- `scripts/lib/market_types.py`: Updated Kalshi sports/eSports regexes and classification logic to correctly handle `game_outcome` and `esports_prop` for eSports contracts.
- `tests/test_kalshi_esports.py`: Added regression coverage for Kalshi eSports routing and market classification.

### Fixed
- `scripts/paper.py`: Fixed model-implied and paper-bundle slice group counts in `open_pick_diagnostics` to use the full open set instead of being truncated by the 10-row example cap.
- `scripts/lib/kalshi.py`: `_is_combo_market` now allows single-match eSports rows even if the ticker contains multi-game grouping tokens.

### Changed
- `scripts/lib/kalshi.py`: `KXCS2GAME`, `KXVALGAME`, and `KXLOLGAME` are now part of the broad `Kalshi live markets` board scan.
- `SKILL.md`, `README.md`, `scripts/lib/ui.py`, `scripts/lib/bird_x.py`, `scripts/lib/youtube_yt.py`, `.claude-plugin/plugin.json`, and `gemini-extension.json`: Updated version to `v1.0.80`.

## [1.0.79] - 2026-04-25

### Added
- `scripts/paper.py`: NBA paper bundle resolver for automatic resolution of multi-leg NBA paper bundles using final ESPN outcomes.
- `scripts/paper.py`: New `paper_bundle_open_slice` and `model_implied_open_slice` in `open_pick_diagnostics` for better visibility into actionable unresolved rows and legacy noise.

### Changed
- `scripts/paper.py`: Refactored `_resolve_nba_pick` to use a reusable `_resolve_nba_game` helper, improving consistency between single-pick and bundle resolution.
- `scripts/paper.py`: `_resolve_pick` now routes `paper_bundle` venues to the new bundle resolver.
- `SKILL.md`, `README.md`, `scripts/lib/ui.py`, `scripts/lib/bird_x.py`, `scripts/lib/youtube_yt.py`, `.claude-plugin/plugin.json`, and `gemini-extension.json`: Updated version to `v1.0.79`.

## [1.0.78] - 2026-04-25

### Changed
- `scripts/last24hours.py` and `scripts/lib/closing_soon.py`: `Kalshi live markets` now runs as a broad Kalshi live-board scan instead of being forced through the closing-soon pipeline.
- `scripts/lib/kalshi.py`: Broad Kalshi live-board discovery now uses direct series routing and a diversity-preserving shortlist across BTC, ETH, AI, Fed/rates, CPI, jobs, and NBA families instead of depending on generic open-market pages.
- `scripts/lib/kalshi.py`: AI and PGA/golf prompts now route into known Kalshi series such as `KXLLM1` and `KXPGATOUR`, improving coverage for live-market surfaces visible in the Kalshi UI.
- `scripts/lib/render.py`: Empty Kalshi live-board output now reports a Kalshi-specific filter message instead of incorrectly describing a Polymarket closing-soon filter.
- `scripts/lib/market_types.py`: PGA/golf championship markets no longer fall through as `esports_title` contracts.
- `tests/test_closing_soon.py`, `tests/test_kalshi.py`, `tests/test_market_types.py`, and `tests/test_forecast_watchlist.py`: Added regressions for Kalshi live-board routing, direct series coverage, candidate diversity, empty-state diagnostics, and PGA market typing.

## [1.0.77] - 2026-04-25

### Changed
- `scripts/paper.py`: Paper watchlist extraction now treats non-closing watchlist rows above 90% or below 10% as too extreme for calibration when no balanced alternative exists, preventing resolved watchlist overconfidence from feeding new paper rows.
- `scripts/paper.py`: Non-closing watchlists now prefer candidates in the 35%-80% probability band once the top row is 80%+, while closing-soon paper rows keep their near-expiry selection behavior.
- `scripts/paper.py`: Dry-run diagnostics can now return `watchlist_extreme_probability_only` or `no_calibration_useful_watchlist_candidate` when a watchlist board is valid for display but not useful enough for paper calibration.
- `AGENTS.md`: Recorded that the repository is public again as of April 25, 2026, so public-readiness is an active requirement for every change.
- `tests/test_paper_ledger.py`: Added regressions for selecting balanced watchlist paper candidates and rejecting extreme-only non-closing watchlist boards.

## [1.0.76] - 2026-04-25

### Changed
- `scripts/paper.py`: `paper.py report --days N` now includes a `resolution_learning_summary` slice that turns resolved paper rows into worst-row examples, high-confidence misses, low-probability hits, subgroup calibration alerts, and concrete audit action items.
- `scripts/paper.py`: Resolution learning excludes legacy noisy-rationale rows, preserving the existing comparable-sample discipline while making recent eSports/NBA/closing-soon failures easier to inspect from report JSON.
- `tests/test_paper_ledger.py`: Added regression coverage for high-confidence miss detection, low-probability hit detection, and subgroup alert generation from resolved paper picks.

## [1.0.75] - 2026-04-24

### Changed
- `scripts/paper.py`: `paper.py report --days N` now includes a `recent_resolution_summary` slice so newly resolved paper rows are visible by domain, pick type, market type, resolution source, and row details without scanning the full ledger.
- `scripts/paper.py`: Open named eSports prop diagnostics now count model-implied rows that are missing degraded-reason metadata, making pre-`v1.0.74` prop rows easier to separate from current diagnostic-rich samples.
- `AGENTS.md` and `README.md`: Documented the release-number rollover convention: continue through `v1.0.99`, then move to `v1.1.1`, with ten-release minor lanes after that instead of using `v1.0.100`.
- `tests/test_paper_ledger.py`: Added regressions for recent-resolution reporting and missing named-prop degraded-reason metadata.

## [1.0.74] - 2026-04-23

### Changed
- `scripts/lib/polymarket.py` and `scripts/lib/forecast.py`: Named Valorant and LoL prop prompts now search more like real threshold-style market titles (`over`, `map 1`, `game 1`, `o/u`) and keep `solo kills` distinct from generic `kills` so same-player props can anchor without reopening bad stat-family matches.
- `scripts/paper.py`: Named eSports prop model-implied rows now record and report prop-specific degraded reason classes such as `no_matching_player_market`, `wrong_stat_family`, and `no_same_day_prop_market`, while preserving the existing paper-only storage contract.
- `tests/test_esports_player_props.py` and `tests/test_paper_ledger.py`: Added regressions for named prop query shaping, threshold-style prop anchor recovery, `solo kills` mismatch rejection, dry-run degraded reason classes, and the new named-prop diagnostics slice in `paper.py report`.

## [1.0.73] - 2026-04-23

### Changed
- `scripts/lib/polymarket.py`: Named eSports player-prop prompts now use domain-aware Polymarket query expansion built from the player token, inferred title subdomain, and primary stat term instead of generic raw-word fanout like `total` and `tonight`.
- `scripts/lib/polymarket.py`: Generic eSports prop discovery remains on the broader CS2/Valorant/LoL search path, so this release narrows only the named-player retrieval surface that was starving forecast anchoring.
- `tests/test_esports_player_props.py`: Added regressions for named Valorant and LoL prop query expansion so TenZ/Faker-style prompts keep the tighter search path and avoid avoidable model-implied fallbacks caused by Polymarket search overhead.

## [1.0.72] - 2026-04-23

### Fixed
- `scripts/last24hours.py`: Explicit venue-scoped closing-soon prompts now honor their venue path during bounded scans, so `Kalshi markets closing soon` no longer spends paper-fast runtime building a Polymarket board first.
- `scripts/lib/market_watchlist.py`: Closing-soon watchlists now fail closed on wrong-venue rows for explicit `Kalshi ...` and `Polymarket ...` prompts, which prevents Polymarket weather rows from displacing the intended Kalshi board.
- `tests/test_forecast_watchlist.py`: Added regression coverage proving that a Kalshi closing-soon topic suppresses mixed-in Polymarket rows and keeps the Kalshi candidate on the rendered board.

## [1.0.71] - 2026-04-22

### Changed
- `fixtures/paper_portfolio.json`: Replaced the dead same-day `NBA paper bundle today` slot with `NBA paper bundle next 2 days`, keeping fixture count unchanged while making the automation target a future-facing NBA bundle window that can actually produce paper-only rows.
- `scripts/lib/sports_schedule.py` and `scripts/lib/paper_bundles.py`: Added explicit NBA bundle-window support for `next 2 days` / `next two days` and tightened empty-window bundle messaging so zero-game windows report as no future NBA games instead of a generic empty watchlist failure.
- `scripts/paper.py`: Dry-run bundle failures now map to bundle-specific reason classes such as `no_future_games_in_window`, `all_games_live_or_final`, `too_few_qualified_direct_markets`, and `bundle_overlap_or_favorite_only` instead of collapsing into `no_compatible_market`.
- `tests/test_paper_bundles.py` and `tests/test_paper_ledger.py`: Added regressions for the new NBA bundle window parsing, empty future-window bundle failure handling, and dry-run bundle-specific reason classes.

## [1.0.70] - 2026-04-22

### Changed
- `scripts/lib/closing_soon.py` and `scripts/last24hours.py`: Expanded the bounded paper fast-path seed packs for broad, crypto, and Kalshi closing-soon scans, added per-seed raw caps plus closing diagnostics, and raised the fast-path breadth enough to recover real near-expiry candidates without reopening timeout behavior.
- `scripts/lib/market_watchlist.py`: Closing-soon ranking now gives extra weight to resolver-friendly near-expiry rows, tight spreads, and usable liquidity while demoting manual-rule rows harder when cleaner candidates are nearby.
- `scripts/paper.py`: Closing-soon paper extraction now uses a topic-aware compatibility gate and more precise dry-run reason classes (`no_near_expiry_candidates`, `all_candidates_effectively_settled`, `all_candidates_low_quality`, `domain_mismatch`), and `report --days N` now includes a `closing_soon_health` slice for venue/market-type visibility.
- `tests/test_closing_soon.py` and `tests/test_paper_ledger.py`: Added regressions for broader closing-soon seed recovery, closing-soon domain-safe paper extraction, closing-soon dry-run reason classes, and the new report health summary.

## [1.0.69] - 2026-04-22

### Changed
- `scripts/lib/forecast.py`: Tightened eSports anchor matching so named CS2 / Valorant / LoL prompts now rank compatible same-day `game_outcome` and `esports_prop` markets by subdomain, entity overlap, market semantics, and end-date compatibility before falling back to model-implied output.
- `scripts/lib/forecast.py`: Generic same-day eSports match prompts now use the stronger compatibility path too, which preserves thin direct-match boards without reopening prop/title fallback leakage.
- `tests/test_esports_player_props.py` and `tests/test_forecast_watchlist.py`: Added regressions for same-day eSports prop preference, named-match anchor selection, and hard rejection of prop-only or match-only fallback on the wrong prompt type.

## [1.0.68] - 2026-04-22

### Changed
- `scripts/paper.py`: Added an explicit open-row eSports audit slice that flags legacy and degraded rows whose stored market text conflicts with their topic domain, subdomain label, or prop contract type.
- `scripts/paper.py`: Open-portfolio warnings now call out these mismatched eSports rows as audit-only samples so historical contamination is harder to misread as live-ready calibration data.
- `tests/test_paper_ledger.py`: Added regression coverage for legacy contaminated eSports rows such as the stored `cs2`/`player_prop` row that actually contains an NBA totals market.

## [1.0.67] - 2026-04-22

### Changed
- `scripts/lib/market_watchlist.py`: Same-day eSports watchlists now keep a tighter end-date window so later-date rows do not crowd the board just because they happen to be high-signal elsewhere in the week.
- `scripts/lib/market_watchlist.py`: Broad eSports boards still fail closed on wrong-domain rows, but they now preserve thin market-signal-driven same-day boards without requiring fragile social evidence to survive first.
- `tests/test_forecast_watchlist.py`: Added regressions for later-date eSports row suppression while keeping generic CS2 watchlists direct-match-only unless the prompt explicitly asks for props.

## [1.0.66] - 2026-04-22

### Changed
- `scripts/paper.py`: Closing-soon paper dry-runs now auto-select a bounded market-only fast path, so `Polymarket markets closing soon`, `Kalshi markets closing soon`, and `crypto markets closing soon tonight` finish with structured statuses instead of timing out behind full-source enrichment.
- `scripts/last24hours.py` and `scripts/lib/closing_soon.py`: Added a paper-watchlist fast mode that caps closing-soon seed breadth and candidate counts while preserving the same venue-specific selection contract for the final paper pick.
- `tests/test_paper_ledger.py` and `tests/test_closing_soon.py`: Added regressions for the bounded closing-soon argument forwarding and the new seed/candidate caps used by the paper fast path.

## [1.0.65] - 2026-04-22

### Changed
- `fixtures/paper_portfolio.json`: Replaced the dead `donk total kills markets to watch today` watchlist slot with `Counter-Strike 2 player props today`, which currently produces a live-ready CS2 prop forecast instead of a permanent `no_compatible_pick`.
- `scripts/paper.py`: Post-`1.0.38` eSports reporting now exposes pick-type visibility and missing-subdomain counts for resolved rows, and the open eSports slice now calls out rows that still lack subdomain labeling so degraded audit samples are visible immediately.
- `tests/test_paper_ledger.py`: Extended eSports paper-report coverage for pick-type visibility, missing-subdomain accounting, and the updated prop-fixture/report expectations.

## [1.0.64] - 2026-04-22

### Fixed
- `scripts/lib/evidence_quality.py`: Named-player eSports prop topics now count as eSports queries when they carry both a recognized player and a stat marker, which closes the last broad-domain hole that let non-eSports rows survive prop compatibility checks.
- `scripts/paper.py`: Paper extraction now rejects eSports watchlist rows that fail final domain, subdomain, or prop-type compatibility before they can be stored, and broad eSports watchlists now infer subdomain from the selected market when the topic itself is intentionally mixed-title.
- `tests/test_paper_ledger.py`: Added regressions proving that wrong-domain NBA rows cannot be stored for `donk total kills markets to watch today`, that broad eSports watchlists retain inferred subdomains, and that dry-run reason classes distinguish wrong-domain from wrong-market-type failures.

## [1.0.63] - 2026-04-22

### Fixed
- `scripts/lib/market_watchlist.py`: Watchlist date and recency checks now key off the report's own generation window instead of the wall clock, which restores deterministic same-day eSports ranking and the intended mixed-board NBA suppression behavior.
- `tests/test_forecast_watchlist.py`: Updated the shared report fixture dates to a stable April 21, 2026 base so relative-date watchlist assertions stay aligned with the market fixtures they are exercising.

## [1.0.62] - 2026-04-22

### Added
- `fixtures/paper_portfolio.json`: Added `esports markets to watch today` so the paper ledger collects a mixed-title eSports watchlist row that already produces a clean same-day candidate in live dry-runs.
- `fixtures/paper_portfolio.json`: Added `CPI in June` as a Kalshi macro forecast sample so the paper ledger keeps collecting post-`v1.0.42` month-compatible CPI anchors outside sports.

### Changed
- `fixtures/paper_portfolio.json`: Replaced `donk player-prop markets to watch today` with `donk total kills markets to watch today` after live testing showed the older wording could still drift into wrong-domain draft markets instead of a usable CS2 prop row.

## [1.0.61] - 2026-04-21

### Added
- `fixtures/paper_portfolio.json`: Narrowed the CS2/Valorant/LoL prop prompts toward named-player total-kills phrasing so the paper runner targets prop surfaces that are more likely to exist live.
- `scripts/paper.py`: Dry-run output now includes `reason_class` for skipped prop topics (`degraded_evidence_only`, `wrong_subdomain`, `no_compatible_market`) and exposes eSports market-type visibility in both the post-`1.0.38` sample and the open-row slice.
- `tests/test_paper_ledger.py`: Added regressions for dry-run reason classes, eSports market-type visibility, and prop-oriented open-slice grouping.

## [1.0.60] - 2026-04-21

### Added
- `scripts/lib/forecast.py`: Added stricter eSports player-prop anchor matching so named CS2/Valorant/LoL prop prompts prefer compatible player+subdomain+stat markets instead of falling back on loose title overlap.
- `scripts/last24hours.py`: Kalshi source health now stays `SKIP` on non-Kalshi eSports surfaces even if the background Kalshi search errors or times out.
- `tests/test_esports_player_props.py` and `tests/test_reddit_bluesky_debug.py`: Added regressions for named prop compatibility, cross-title prop rejection, and eSports Kalshi `SKIP` footer behavior.

## [1.0.59] - 2026-04-21

### Added
- `scripts/lib/market_watchlist.py`: Tightened eSports prop watchlist admission so explicit CS2/Valorant/LoL prop prompts only admit compatible `esports_prop` rows and reject wrong-domain markets before ranking.
- `scripts/lib/render.py`: Added a prop-specific empty-state explanation when no compatible same-day eSports prop rows survive the domain, subdomain, and date/type filters.
- `tests/test_forecast_watchlist.py`: Added regressions for wrong-domain market rejection and precise eSports prop empty-state rendering.

## [1.0.58] - 2026-04-21

### Added
- `fixtures/paper_portfolio.json`: Added Valorant and LoL player-prop entries (`TenZ kills vs Sentinels tonight`, `Faker solo kills tonight`) to the daily tracking ledger.
- `tests/test_esports_player_props.py`: Extended coverage with `ValorantAndLoLSurfacingTests` to ensure end-to-end surfacing parity for Valorant and LoL player-prop queries analogous to CS2.

## [1.0.57] - 2026-04-21

### Added
- `scripts/lib/market_watchlist.py`: Tuned ranking for player-prop queries via `_esports_prop_rank_adjust()` to weigh evidence and movement more heavily than volume/open-interest, as prop markets typically move thin. Lowered the near-certainty penalty for `esports_prop` markets in `_near_certain_penalty()` since they behave differently from game-outcome pins.
- `scripts/lib/forecast.py`: "Why this is the current line" rationale for player-prop anchors now extracts and explicitly names the player and stat. Implemented "Option 3" Sportsbook fold-in: when a player-prop forecast fires and `sportsbook` is available, the rationale seamlessly integrates FanDuel/DraftKings consensus lines without outranking the primary Polymarket/Kalshi anchor.

## [1.0.56] - 2026-04-21

### Added
- Wired the v1.0.55 CS2/Valorant/LoL player-prop detection helpers through forecast and watchlist pipes. Player-prop queries now return `esports_prop` markets and bias catalyst snippets toward the named player.
- `scripts/lib/market_watchlist.py`: Expanded `_is_explicit_esports_prop_prompt()` to use `eq.extract_esports_players(topic)` to unsuppress the `esports_prop` branch for player-named queries. Added `_esports_player_name_match_bonus()` to bump relevance scores when the market text mentions the named player.
- `scripts/lib/forecast.py`: Updated `_is_direct_game_market()` with an opt-in `allow_esports_prop` parameter to allow player-prop markets in single-market forecasts. Skipped the eSports match-slate branch for player-prop queries.
- `scripts/lib/evidence_quality.py`: Updated `is_esports_rationale_evidence()` to accept `topic` and bypass strict noise-term rejection for evidence snippets that mention the queried player. Updated callers in `market_watchlist.py`, `forecast.py`, and `render.py` to pass the `topic`.
- `fixtures/paper_portfolio.json`: Added "donk kills vs Vitality tonight" (forecast) and "CS2 player-prop markets to watch today" (watchlist) test entries.
- `tests/test_esports_player_props.py`: Added end-to-end surfacing tests for the single-market forecast path and the watchlist relevance bonuses.

## [1.0.55] - 2026-04-21

### Added
- CS2/Valorant/LoL player-prop detection groundwork in `scripts/lib/evidence_quality.py`: curated `CS2_PLAYER_TOKENS` / `VALORANT_PLAYER_TOKENS` / `LOL_PLAYER_TOKENS` rosters plus helpers `extract_esports_players(text, subdomain=...)`, `extract_cs2_players()`, `is_cs2_player_text()`, `has_player_prop_stat_marker()`, and `is_esports_player_prop_query()` which requires co-occurring eSports + prop signals so unrelated text containing a handle ("donk the dictator") does not trip.
- `scripts/lib/forecast.py::_is_esports_player_prop_query` thin wrapper on the eq helper, kept disjoint from `_is_esports_match_query` which continues to reject kills/props/handicap outright. This preserves the match-slate path while opening a parallel player-prop path for v1.0.56 to wire.
- `scripts/lib/market_types.py::_ESPORTS_PROP_MARKERS` extended with `headshot`, `adr`, `first kill`, `first blood`, `1v1`, `clutch`, `entry kill`, `mvp`, `bomb plant`, `pistol round`, `assists`, `deaths`, `kd`, `rating` so `classify_market()` tags player-prop titles as `esports_prop`.
- `tests/test_esports_player_props.py` (23 tests) covers CS2/Valorant/LoL roster extraction, cross-subdomain isolation, player-prop query classifier (positive + negative cases), disjointness with match-slate classification, market-type tagging, and stat-marker helper.

### Notes
- v1.0.55 ships detection helpers and tests only — no changes to what gets surfaced. Player-prop queries still route through the existing forecast/watchlist paths until v1.0.56 wires the new classifier into `_candidate_to_watch_item`, `_is_direct_game_market`, and the forecast slate branch.

## [1.0.54] - 2026-04-21

### Added
- `scripts/lib/sportsbook.py` — sportsbook odds context tier backed by the-odds-api.com (FanDuel, DraftKings, BetMGM, Caesars). Covers pre-game moneyline / spread / total lines for NBA, NFL, MLB, NHL. Includes `search_sportsbook()` with graceful no-key fallback, `parse_sportsbook_response()` flattening into per-quote dicts, `consensus_rows()` collapsing multi-book quotes into best/worst/avg rows, American↔decimal↔implied-probability conversions, sport detection from team/league mentions, and a monthly usage ledger at `~/.local/share/last24hours/sportsbook_usage.json` with a 480/500-call safety cap.
- `scripts/lib/casino_reference.py` — static casino-game house-edge reference (blackjack, European/American roulette, craps pass line, baccarat banker, 9/6 video poker, typical Strip slots) with keyword lookup (`lookup_casino_context()`) and `is_casino_query()` helper. Anchors informational context when users ask about casino markets; no live scraping.
- `scripts/lib/env.py` — new config keys `ODDS_API_KEY`, `LAST24HOURS_SPORTSBOOK_BOOKS`, `LAST24HOURS_DISABLE_SPORTSBOOK`, plus `is_sportsbook_available()` / `is_casino_context_available()` helpers.
- `scripts/lib/query_type.py` — `sportsbook` is now a tier-2 source for both `prediction` and `market_watchlist` queries (opt-in via `--search=sportsbook` or automatic when the API key is configured).
- `scripts/last24hours.py --diagnose` surfaces sportsbook availability, monthly API-call usage, and casino-reference availability.
- `tests/test_sportsbook.py` (27 tests) + `tests/test_casino_reference.py` (17 tests) covering odds math, sport detection, graceful missing-key behavior, HTTP-error capture, monthly-cap short-circuit, response parsing, consensus collapsing, keyword lookup, and false-positive avoidance for terms like "21 savage".

### Notes
- Direct scraping of fanduel.com / sportsbook.draftkings.com is forbidden by their ToS and their line data lives behind authenticated XHR endpoints; the-odds-api.com (free tier: 500 req/month) is the chosen aggregator. When no `ODDS_API_KEY` is configured, the skill silently degrades — no traceback, no empty-result noise.
- Sportsbook items are scoped as *context*, not anchors. Full forecast/watchlist fan-out wiring and rationale surfacing land in subsequent releases alongside the CS2 player-prop batch.

## [1.0.53] - 2026-04-21

### Fixed
- `market_watchlist._item_effectively_settled()` rejects watchlist candidates pinned at >=98.5% / <=1.5% with <=1¢ spread so effectively-settled markets (e.g. an eSports Game-2 winner pinned at 100%/0%) stop leaking into generic watchlists; in closing-mode the gate defers only when the item's `closing_soon_reason` is `live_sports` or `starting_soon`.
- Tightened the eSports game-outcome bypass in `_candidate_to_watch_item`: a high-movement near-pinned market (>=98.5% / <=1.5%) is treated as settlement convergence and never bypasses the pinned-probability filter.
- `_search_reddit_many` now runs each per-topic worker with its own `max(20, total_budget / topic_count)` timeout and returns partial results on timeout rather than discarding completed subqueries when a single subquery hangs. The outer 60s reddit-future budget stays as a safety cap.
- Added `tests/test_forecast_watchlist.py::EffectivelySettledWatchlistTests` and `tests/test_reddit_fanout.py` regression coverage for both fixes.

## [1.0.52] - 2026-04-21

### Fixed
- Added `tests/test_kalshi_nba.py` regression coverage for Kalshi-led NBA slate forecasts: Kalshi compact-ticker team codes align with full team-name matchup topics via `_market_matches_matchup`, the reverse match rejects wrong-opponent tickers, stale Kalshi game dates are rejected by `_sports_market_date_compatible` when the slate target is a later day, fresh dates are accepted, a Kalshi-only single matchup topic still produces a Kalshi-anchored forecast when Polymarket is empty, and a mixed Kalshi+Polymarket slate surfaces both games with the higher-scoring Polymarket anchor leading.

## [1.0.51] - 2026-04-21

### Added
- `paper._resolve_crypto_pick()` closes the BTC/ETH/SOL paper-pick loop without manual input: it parses asset symbol, direction (`above`/`below`), and threshold (with `k`/`m`/`b` suffix and comma-separated amounts) from the topic, derives a resolution date from `end_date` or phrases like `today` / `tomorrow` / `this week` / `this month`, fetches the spot price from CoinGecko (`/simple/price`) with a Kraken public ticker fallback, and returns a `(status, value, "coingecko")` tuple consistent with the existing NBA and weather resolvers.
- `_resolve_pick()` now dispatches to the crypto resolver when `_domain(topic) == "crypto"`, and the `has_auto_resolver` allowlist accepts `coingecko` as a resolution source plus crypto-domain topics so the paper ledger no longer treats the portfolio's `Bitcoin above 100k this week` entry as manual-only.

### Fixed
- Added `test_paper_ledger` regressions covering above-threshold YES, below-threshold NO, reverse-direction `below` parsing, future-date skip, unparseable-threshold manual fallback, and `_parse_crypto_threshold` k-suffix plus comma-amount handling.

## [1.0.50] - 2026-04-21

### Added
- `closing_soon.scan_kalshi_closing_soon()` scans Kalshi for near-expiry contracts using each market's `close_time`, with bounded window filtering, zero-liquidity rejection, effectively-settled skipping, and nearest-close-first ranking that mirrors the Polymarket pattern shipped in v1.0.14.
- `parse_kalshi_response` now emits `end_datetime` (full timestamp) alongside the existing date-only `end_date` so downstream consumers can compute minutes-to-close without losing precision.
- Paper portfolio carries a `Kalshi markets closing soon` entry with `--closing-window-hours 6` so Kalshi closing-soon coverage shows up in the calibration ledger.

### Changed
- When a closing-soon or market-watchlist query runs outside live-sports mode, `last24hours.py` now also performs the Kalshi closing-soon scan and merges the results into the deduplicated Kalshi list, emitting a `kalshi-closing-candidates:N` planning note.

### Fixed
- Added `test_closing_soon.ScanKalshiClosingSoonTests` regressions covering near-expiry inclusion, expired/out-of-window rejection, zero-liquidity rejection, effectively-settled skipping, and nearest-close-first ranking.

## [1.0.49] - 2026-04-21

### Added
- `evidence_quality.esports_subdomain_of()` plus `is_valorant_market_text` / `is_valorant_query` / `is_lol_market_text` / `is_lol_query` helpers so Valorant and League of Legends prompts get the same direct-match anchoring and cross-title rejection that CS2 prompts shipped in v1.0.38–1.0.45.
- Paper portfolio entries for Valorant and League of Legends (watchlist + forecast each) so calibration coverage is symmetric with CS2.

### Changed
- Polymarket, Kalshi, and rationale-evidence filtering in `forecast.py` and `render.py` now route eSports cross-title rejection through the generic subdomain helper instead of CS2-specific checks, so Valorant and LoL prompts reject CS2/cross-title rows automatically.
- `paper._subdomain()` now emits `valorant` and `lol` labels alongside `cs2`, so the v1.0.48 scope-filter refactor surfaces them in report rollups without further changes.

### Fixed
- Added `tests/test_esports.py` regression coverage for CS2/Valorant/LoL market-text detection, subdomain routing, and cross-title mismatch rejection.

## [1.0.48] - 2026-04-21

### Changed
- `paper.py` calibration summary now builds per-axis group rollups (`venue`, `anchor_source`, `pick_type`, `market_type`, `confidence`, `domain`, `subdomain`, `probability_bucket`, `watchlist_scope`) through a single `_add_scope_groups()` / `_scope_summary()` pair so new sports subdomains can slot in without duplicated loops.
- Output JSON keys and shapes are unchanged; the refactor is backward-compatible for existing `paper.py report` consumers.

### Fixed
- Added regressions asserting axis coverage and synthetic `valorant` / `lol` subdomain grouping so future eSports subdomains stay addressable.

## [1.0.47] - 2026-04-21

### Changed
- Refreshed README, skill instructions, and agent development guides to showcase current forecasting, watchlist, closing-soon, live-sports, paper-ledger, cleanup, and testing workflows.
- Backfilled explicit release-discipline guidance after the published v1.0.17 -> v1.0.23 history jump so future work must ship as one versioned commit and push per patch release without silent gaps.

## [1.0.46] - 2026-04-21

### Changed
- `paper.py daily --dry-run` now uses bounded per-topic probes, returns explicit `ready`, `duplicate_skip`, `degraded_run`, `no_compatible_pick`, and `error` states, and emits topic progress while it evaluates the portfolio.
- `paper.py report` now exposes a dedicated open eSports slice so unresolved CS2 rows are visible without scanning the full ledger payload.
- Post-`1.0.38` eSports sample reporting now includes clearer empty-state operator text when the reporting slice exists but no rows have resolved yet.

### Fixed
- Added regressions for dry-run timeout/error handling, open eSports reporting slices, and the new operator-facing empty-state text.

## [1.0.45] - 2026-04-21

### Changed
- Generic `Counter-Strike 2 matches today` forecasts now accept clean direct CS2 match rows even when market typing is still sparse, reducing unnecessary model-implied fallbacks.
- CS2 forecast boards now reject non-CS2 titles from the anchor path, while Kalshi source diagnostics show `SKIP` on eSports surfaces where Kalshi is not part of the intended venue path.
- Tightened Kalshi macro compatibility so CPI and jobs prompts do not anchor on the wrong macro family even when the month matches.

### Fixed
- Added regressions for CS2 unknown direct-match anchoring, CS2 cross-title rejection, Kalshi `SKIP` rendering, and CPI/jobs macro mismatch filtering.

## [1.0.44] - 2026-04-21

### Changed
- Tightened same-day eSports watchlist ranking so direct match rows outrank thin near-certain stale rows more often, with stricter date filtering for `today` prompts.
- Rejected generic watch-live, score repost, and tournament-listing chatter from CS2/eSports catalyst summaries while keeping market-signal-driven rows visible.
- Broad `esports markets to watch today` boards now preserve mixed-title coverage more intentionally instead of letting one stale cluster dominate.

### Fixed
- Added regressions for CS2 watch-live catalyst rejection, same-day rendered-board date filtering, and mixed-title eSports watchlist shaping.

## [1.0.43] - 2026-04-21

### Added
- `paper.py report` now includes a `post_1_0_38_esports_sample` slice so new CS2/eSports calibration rows can be audited separately from older paper history

### Changed
- `paper.py daily --dry-run` now executes the fixture logic far enough to report per-topic readiness, duplicate-skip outcomes, degraded runs, and no-compatible-pick outcomes instead of only echoing the topic list
- eSports report output keeps `domain: esports` and `subdomain: cs2` visible in comparable-sample summaries without changing the SQLite schema

### Fixed
- Added regression coverage for dry-run warning clarity and the new post-1.0.38 eSports sample slice without regressing existing NBA, macro, crypto, and legacy-noisy report diagnostics

## [1.0.42] - 2026-04-21

### Changed
- Kalshi source-health tracking now distinguishes successful-but-empty prediction runs from degraded or errored runs, and the compact source footer reports those states explicitly
- Macro Kalshi compatibility is stricter for Fed-cut prompts so neighboring threshold ladders no longer qualify as fallback anchors for narrower policy-direction questions

### Fixed
- Added regressions for empty Kalshi source-status rendering, degraded Kalshi status bucketing, and threshold-ladder non-anchoring on Fed cut prompts

## [1.0.41] - 2026-04-21

### Changed
- Tightened CS2 and broad eSports runtime filtering so degraded forecast output suppresses weak X noise, reply chatter, outage/update spam, and generic non-match discussion
- Hardened eSports watchlist shaping for `today` prompts by filtering non-eSports leakage, demoting stale near-certain rows, and keeping mixed-title boards focused on same-day direct match markets

### Fixed
- CS2 and broad eSports watchlists no longer surface unrelated recruiting or scholarship chatter as catalyst evidence
- Added regression coverage for short-tag CS2 match handling, degraded compact-source suppression, mixed-title eSports watchlists, unrelated catalyst rejection, and same-day board filtering

## [1.0.40] - 2026-04-21

### Added
- Two paper-only CS2 portfolio entries: one same-day CS2 watchlist sample and one same-day CS2 forecast sample
- Paper notes and report rollups now track eSports `subdomain` metadata, with `cs2` available for future calibration slices

### Changed
- Paper extraction now tags forecast, watchlist, and bundle notes with `domain` plus `subdomain` metadata without changing the SQLite schema
- Paper report summaries and open-pick diagnostics now expose `subdomain:*` groupings alongside the existing domain rollups

### Fixed
- `paper.py daily --dry-run` now includes the CS2 calibration topics in the shipped portfolio fixture without regressing existing NBA, macro, crypto, weather, or tech diagnostics

## [1.0.39] - 2026-04-21

### Added
- CS2 match forecasting now supports direct multi-row slate boards for prompts like `Counter-Strike 2 matches today`, anchored on clean same-day Polymarket match markets
- Shared eSports forecast logic now uses roster, patch, veto, bracket, and tournament-context catalyst framing instead of borrowing NBA-style lineup/rest language

### Changed
- Direct eSports matchup forecasts now treat CS2 match boards as date-compatible slate forecasts instead of collapsing to a single generic top market
- Explicit CS2 title-market forecasts now use eSports evidence scoring, so map-pool prompts can anchor on cleaner map-pool context without promoting generic betting chatter into the lead line

### Fixed
- CS2 `today` forecast boards no longer leak later-date match rows through Polymarket `updatedAt` timestamps
- CS2 map-pool forecasts now reject betting-style phrases such as `streak starter` and `line feels too low` from the main rationale path

## [1.0.38] - 2026-04-21

### Added
- First-class eSports / CS2 watchlist routing, query detection, market typing, and compact market labels for direct match markets, eSports props, and eSports title markets
- Counter-Strike-focused watchlist search aliases so `Counter-Strike 2 markets to watch today` discovers real Polymarket CS2 match boards instead of empty output

### Changed
- Generic CS2 watchlists now rank direct same-day Counter-Strike match winner markets first and suppress map props plus long-dated map-pool/title contracts unless the prompt asks for them explicitly
- Generic eSports watchlists now use stronger domain seeds across Counter-Strike, Valorant, and LoL instead of relying on incidental broad search matches

### Fixed
- CS2 watchlists no longer misread unrelated `strike` markets as Counter-Strike contracts
- Explicit CS2 map-pool prompts still surface title-market rows after the stronger generic CS2 filtering
- CS2 catalyst filtering now rejects generic dev-log style noise in watchlist ranking tests

## [1.0.37] - 2026-04-21

### Fixed
- Kalshi macro search now routes explicit Fed/rates prompts into direct `KXFEDDECISION` series coverage instead of relying only on broad rate-threshold ladders, which lets `Fed rate cut by June` return a real June Kalshi anchor.
- Kalshi macro event parsing now understands month-only event tickers such as `KXFEDDECISION-26JUN`, improving month matching and preventing broad macro retrieval from displacing explicit month-targeted Fed contracts.
- Kalshi Fed/rates, CPI, and jobs contracts now normalize as `macro_binary`, and forecast anchoring rejects broad rate-threshold rows when the prompt explicitly asks for a cut/hike-style contract.

### Changed
- The deterministic macro planner now keeps explicit month/date macro prompts tight instead of broadening them into generic `Fed rate cuts` subqueries that can swamp the intended month-specific market.

### Tested
- Added regressions for Kalshi Fed series routing, Kalshi Fed contract classification, month-specific Kalshi macro anchoring, and planner tightening for explicit-month Fed prompts.

## [1.0.36] - 2026-04-21

### Changed
- NBA slate forecasts now gather clean direct-game markets from both Polymarket and Kalshi instead of iterating Polymarket alone, which allows Kalshi-only slate boards when Kalshi has the only date-compatible game contracts
- Kalshi/Polymarket NBA pairing now uses Kalshi NBA event-ticker team codes when matching same-game contracts, so city-style Kalshi labels can line up with nickname-style Polymarket labels
- Market watchlists no longer force a near-cutoff Kalshi row into the top set just for venue coverage; Kalshi rows now stay or drop on the same structural ranking basis as other candidates

### Fixed
- Kalshi matchup filtering for NBA-expanded search topics now accepts NBA team codes from Kalshi tickers, which stops valid `Phoenix at Oklahoma City` rows from dropping out when the expanded topic uses `Suns vs. Thunder`

### Tested
- Added regressions for Kalshi/Polymarket NBA matchup alignment, Kalshi-only NBA slate forecasts, and NBA matchup filtering through Kalshi event-ticker team codes

## [1.0.35] - 2026-04-21

### Fixed
- Kalshi sports date matching now reads compact ticker/event dates such as `26APR23`, which prevents date-specific sports forecasts from treating out-of-window Kalshi contracts as date-compatible by default
- Direct Kalshi sports searches now filter candidate markets to the requested topic day when prompts specify `today`, `tomorrow`, or an explicit sports date, instead of leaving that discipline to downstream NBA wrapper behavior alone

### Tested
- Added deterministic Kalshi regressions for in-window sports-market filtering and Kalshi compact ticker date compatibility

## [1.0.34] - 2026-04-21

### Fixed
- Kalshi NBA winner contracts such as `Game 3: New York at Atlanta Winner?` now classify as direct `game_outcome` markets instead of falling through as `unknown`, which lets them survive NBA mixed-watchlist scope filtering
- Kalshi sports series winner contracts now classify as `futures` so explicit series-heavy sports prompts can distinguish broader series markets from single-game rows

### Tested
- Added regressions for Kalshi NBA winner contract classification, Kalshi NBA series contract classification, and Kalshi NBA game rows surviving mixed-watchlist scope filtering

## [1.0.33] - 2026-04-21

### Added
- Mixed NBA watchlist rows now carry explicit `watchlist_scope` metadata into the paper ledger so `paper.py report` can separate NBA game-monitoring rows from playoff-series rows without any schema migration
- `paper.py report` now emits a `post_1_0_30_nba_watchlist_sample` rollup plus open-NBA scope diagnostics, including mixed-scope clusters when a same-matchup game row and series row are both open

### Changed
- `NBA markets to watch today` remains a mixed board, but the ranking now treats same-day game rows and playoff-series rows as distinct classes so direct games anchor the board while series rows must clear a higher signal bar to stay in the top set
- Compact NBA watchlist rendering now labels mixed-board rows explicitly as `Game outcome` or `Playoff series`, which makes same-day monitoring and broader series-state monitoring easier to read
- Paper extraction from mixed NBA watchlists now prefers a near-tied direct game row over a same-matchup series row for day-of-game prompts, while still allowing clearly stronger series rows to win when they materially outrank the game row

### Tested
- Added regressions for mixed NBA watchlist ordering, explicit series labeling, weak-series suppression, mixed-scope paper extraction, and NBA watchlist report rollups by `watchlist_scope`

## [1.0.32] - 2026-04-21

### Added
- `paper.py report` now breaks legacy noisy open rows out by failure reason and includes compact example rows so older sportsbook, media-guide, recap, and promo rationale is visible without rewriting ledger history

### Fixed
- Historical paper-ledger audit logic now flags legacy sports rationale noise, including ATS-style sportsbook copy, how-to-watch text, ticket chatter, and prior-game recap phrasing, instead of only catching macro/crypto-style spam

### Tested
- Added ledger regressions for legacy sports rationale detection, noisy-reason rollups, example-row surfacing, and comparable-summary exclusion of sportsbook-style resolved rows

## [1.0.31] - 2026-04-21

### Fixed
- NBA slate/date-window forecasts now reject ATS-style sportsbook copy, how-to-watch media guides, ticket chatter, and prior-game recap language from both `why_line` selection and compact sports source sections
- NBA slate/date-window prompts now behave as first-class slate queries for rendering and direct-game market filtering, so primary pricing sections stay limited to direct in-window game-outcome rows
- Sports rationale quality now requires cleaner injury, lineup, rest, elimination/clinch, or exact-date line-movement context instead of treating generic playoff or seed wording as forecast signal

### Tested
- Added regressions for ATS-angle false positives, how-to-watch suppression, past-game recap suppression, NBA date-window slate detection, and direct-game-only slate market rendering

## [1.0.28] - 2026-04-20

### Added
- `paper.py report` now emits a `current_skill_comparable_sample` rollup for resolved rows that are both current-version comparable and free of legacy noisy rationale text
- Open-paper diagnostics now break out version eras, legacy-noisy groups, source-health status rollups, and duplicate-cluster summaries so current post-hardening samples are easier to separate from older history

### Changed
- Duplicate-open-row diagnostics now distinguish legacy duplicate noise from current post-dedupe-era rows without rewriting any historical paper records

### Tested
- Added paper-ledger regressions for current-skill comparable rollups, legacy-noisy breakdowns, duplicate-era separation, and stored source-health status aggregation

## [1.0.29] - 2026-04-20

### Changed
- Tightened degraded crypto compact-source filtering for threshold forecasts so weak social chatter no longer survives just because it mentions `100k` plus generic ETF commentary
- Threshold parsing now ignores numbers embedded in handles and similar alphanumeric tokens, which prevents false threshold matches in crypto social evidence

### Tested
- Added crypto forecast regressions for threshold-mismatch social chatter and threshold-matched ETF opinion chatter that still lacks real market-structure context

## [1.0.30] - 2026-04-21

### Changed
- Degraded crypto threshold forecasts now synthesize a threshold-aware `why_line` from clean X/web market context instead of quoting raw social posts directly
- Crypto threshold summaries now call out when the best evidence is still materially below the requested target, which makes sparse model-implied forecasts more informative without overstating conviction

### Tested
- Added regressions for threshold-aware crypto summaries built from lower-price market context and from social market-color that mentions the target but is still better handled as a synthesized summary

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
