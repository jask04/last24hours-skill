# /last24hours v1.0.79.

`/last24hours` is a real-time forecasting and market-watchlist skill. It uses the last 24 hours of market, social, and web evidence to produce a probability forecast first, then explains the evidence and uncertainty behind it. It can also run one-shot topic-scoped market discovery for prompts such as `NBA markets to watch today` or `macro markets to watch around Fed cuts`.

Codex chat is the primary target UX. The compact output is designed to open with a forecast block that feels native in chat, with raw evidence sections following underneath for inspection.

Forecasts are now market-anchored by default. When Polymarket and Kalshi both exist for the same outcome, the skill blends them with liquidity/quality weighting and widens uncertainty when the spread is meaningful.

When no clean market or official source can anchor a forecast, the output now marks the run as degraded so model-implied probabilities are not mistaken for market-backed edges.

Market-watchlist mode is separate from forecasting mode. It ranks Polymarket and Kalshi markets by topic relevance, exchange-native signal quality, 24h volume, liquidity/open interest, bid-ask spread, recent movement, catalyst evidence, and cross-market disagreement. The output is informational market monitoring, not trade execution or allocation advice.

For mixed NBA watchlist prompts such as `NBA markets to watch today`, the board can now intentionally include both direct same-day game markets and playoff series markets. Direct games still anchor the board when they are clean and relevant, while series rows stay labeled separately as broader series-state monitoring instead of blending into the game board silently.

Closing-soon watchlist mode is available for prompts such as `Polymarket markets closing soon`, `crypto markets closing soon tonight`, or `live sports games on Polymarket right now`. It scans near-expiry Polymarket markets, preserves close datetimes, ranks by minutes to close plus market quality, and can label matching NBA/MLB/NHL/NFL games as live or starting soon from ESPN public scoreboards. Live-sports scans only surface direct matching game-outcome markets; series, futures, totals, props, and wrong-matchup markets are rejected with diagnostics. Catalyst snippets must match the specific market domain and entity; when no clean external catalyst clears the filter, rankings are labeled as market-signal driven. Fast-moving lines must be verified in the Polymarket UI before relying on them.

NBA date-window scans can expand prompts such as `NBA games April 20 2026 through April 22 2026` into ESPN-backed matchup searches. Bundle-intent prompts such as `NBA paper bundle ideas April 20 through April 22` produce paper-only multi-leg watchlists from direct ESPN-matched game-outcome markets, with independence-baseline probability math, correlation warnings, and fragility notes.

Paper forecast tracking is available for calibration work. The paper ledger records hypothetical daily forecasts, resolves them later when public market outcomes are available, scores calibration, tracks whether the portfolio is leaning on easy favorites or longshots, and prints suggested system improvements for review. New paper records include the skill version so calibration can be compared across forecast-engine changes. It does not place trades, size positions, recommend stakes, or automatically change forecast weights.

For sports, the market sets the number and social/web evidence mainly explains the line. The skill now prefers concrete injuries, availability, lineups, rest, playoff incentives, and exact-date line movement over betting-bot chatter, ticket resale posts, generic previews, historical clips, or vague hype. Low-signal sports sources may remain visible for auditability, but they should not become the forecast rationale.
Slate explanations are matchup-scoped, so a status note for one game should not explain another game's forecast.

For weather and macro/politics, the skill now suppresses weak supporting evidence hard. If no high-signal weather, policy, data, polling, or market-repricing evidence is available, the forecast stays market-led or model-implied and says so directly instead of filling the answer with noisy social chatter.

For supported U.S. weather prompts, `/last24hours` now uses the public National Weather Service API as an official no-key anchor. If no clean market exists for a prompt such as `NYC rain tomorrow`, NWS precipitation probability can lead the forecast instead of social chatter.

The skill is optimized for:
- prediction markets
- market-watchlist discovery
- sports outcomes
- weather outcomes
- elections and politics
- macro and event-driven forecasts

Polymarket and Kalshi are the primary market anchors. X, Reddit, Hacker News, and the web are supporting inputs used to explain, pressure-test, or challenge the market line.

National Weather Service forecasts are the official anchor for supported U.S. weather prompts when a clean Polymarket/Kalshi market is not available.

For broad NBA slate prompts such as `tomorrows nba games`, the compact output now opens with a per-game slate forecast board before the raw evidence sections.

For date-specific sports prompts, forecast anchoring rejects stale same-team markets when the market date clearly conflicts with the requested game date.

Recent upstream `last30days` v3 ideas are adapted selectively: deterministic search planning, cross-source evidence fusion, small evidence clustering, and per-author caps. These only improve retrieval and explanations; they do not replace the market-anchored forecast engine.

Built on [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn.

## Feature Tour

Use `/last24hours` for five related workflows:

| Workflow | What it does | Example |
| --- | --- | --- |
| Probability forecast | Produces a market-anchored forecast with uncertainty and catalysts | `/last24hours Bitcoin above 100k this week` |
| Sports slate forecast | Expands broad NBA slate prompts into matchup-specific forecasts | `/last24hours tomorrows nba games` |
| Sports date-window scan | Expands bounded NBA date windows into matchup-specific searches | `/last24hours NBA games April 20 2026 through April 22 2026` |
| Market watchlist | Ranks topic-scoped Polymarket/Kalshi markets for monitoring | `/last24hours NBA markets to watch today` |
| Closing-soon scanner | Finds near-expiry Polymarket markets and live/starting-soon sports markets | `/last24hours Polymarket markets closing soon` |
| Paper bundles | Builds paper-only multi-leg NBA watchlist bundles with correlation warnings | `/last24hours NBA paper bundle ideas April 20 through April 22` |
| Paper forecast ledger | Records hypothetical forecasts, resolves them later, and reports calibration | `python3 scripts/paper.py daily --portfolio fixtures/paper_portfolio.json --quick` |

Current notable capabilities:
- Polymarket and Kalshi market anchoring with liquidity/quality-aware blending when both venues describe the same outcome.
- Threshold-aware forecast matching, so `Bitcoin above 100k this week` does not anchor to unrelated `$70k` or range markets.
- Official National Weather Service anchoring for supported U.S. weather prompts such as `NYC rain tomorrow`.
- ESPN-backed NBA slate and paper-pick resolution, plus live/starting-soon detection for NBA, MLB, NHL, and NFL watchlists.
- ESPN-backed NBA date-window expansion and paper-only multi-leg bundle output for direct ESPN-matched game-outcome markets.
- Mixed NBA watchlists that label direct rows as `Game outcome` and series rows as `Playoff series`, with paper-ledger scope metadata so NBA watchlist calibration can be split cleanly between game and series monitoring.
- Kalshi NBA winner contracts now classify as direct game-outcome markets, so Kalshi sports rows can clear NBA watchlist scope filters instead of dropping out as unknown contracts.
- Kalshi sports searches now respect day-specific topic windows more directly, using compact ticker/event dates so `today`, `tomorrow`, and explicit sports dates stop pulling unrelated future game contracts into the candidate set.
- Kalshi can now lead NBA slate forecasts directly when it has the cleanest or only date-compatible game markets, instead of being limited to a blend/attachment role behind Polymarket.
- Closing-soon Polymarket scanning with full close datetimes, minutes-to-close, liquidity/spread, 24h movement, and resolvability notes.
- Market-watchlist catalyst filtering that rejects unrelated promo posts, picks/parlay chatter, and domain-mismatched snippets.
- Paper-only calibration loop with Brier score, log loss, probability buckets, favorite/longshot diagnostics, and conservative suggestions.
- Disposable raw markdown report cleanup with `--save-dir`, `--save-retention-days`, and `--clean-save-dir`.
- Deterministic relative-date testing with `--as-of-date YYYY-MM-DD` or `LAST24HOURS_AS_OF_DATE`.

## What It Returns

For forecastable queries, the default answer shape is:

```text
Forecast: 62-66% - slight lean to yes

Market view:
- Polymarket: 64%, up 6% today
- Kalshi: 60%, flat today

Evidence:
- 3-5 highest-signal drivers from X, Reddit, web, HN, and optional video/social

Uncertainty:
- unresolved or conflicting signals

What changes the number:
- concrete catalysts that move the probability up or down
```

If no live market exists, `/last24hours` still returns a model-implied forecast, but marks confidence lower and leans more heavily on non-market evidence.

For market-watchlist queries, the default answer shape is:

```text
Market Picks To Watch

Pick: Polymarket or Kalshi market, outcome label, and implied probability
Timing: close datetime, minutes to close, and settlement/resolvability notes when applicable
Why it ranks: market depth, movement, catalyst context, closing-soon signal, or cross-market signal
Market signal: price, 24h move, spread, 24h volume, liquidity, open interest, and signal-quality notes
Catalyst / evidence: X, Reddit, web, or HN context when it clears market-specific quality filters
Risk / what would change it: why the ranking could break or need revision
```

If the request is too broad, the skill returns a lower-confidence watchlist using only high-quality available candidates. If no clean candidates exist, it says `No high-quality market picks found` and lists the filters that failed. If market data is useful but external catalyst evidence is noisy, the item stays market-signal driven and says `Catalyst context is thin; ranking is mostly market-signal driven.`

## Source Priority

For prediction queries:
1. Kalshi
2. Polymarket
3. X
4. Reddit
5. Relevant web
6. Hacker News

For supported U.S. weather queries, the National Weather Service forecast is used as a first-class anchor before falling back to model-implied weather estimates.

YouTube, TikTok, Instagram, Bluesky, and Truth Social are supporting sources unless explicitly requested.

For market-watchlist queries:
1. Kalshi
2. Polymarket
3. Relevant web
4. X
5. Reddit
6. Hacker News

Video/social expansion is opt-in for watchlist prompts unless explicitly requested.

Search planning is deterministic-first. Quick mode expands to a small set of exact market/topic queries and does not call extra entity-resolution web searches. Default/deep mode records native-web availability for future bounded entity resolution while preserving clean fallback behavior.

Supporting evidence is fused across X, Reddit, web, HN, Bluesky, and Truth Social with source weights, domain quality filters, light clustering, and per-author caps. This selects cleaner drivers for `Why this is the current line` and market-watchlist catalyst notes without letting social evidence move a clean market anchor. Market-watchlist catalyst notes also reject generic promotional posts, signal-room pitches, picks/parlay chatter, and domain-mismatched snippets.

## Release Discipline

- Do not skip release numbers within the active version lane. Each shipped version should map to one focused commit and one push.
- Continue the current `v1.0.x` lane through `v1.0.99`; the next release after that is `v1.1.1`, not `v1.0.100`.
- After `v1.1.1`, use short ten-release minor lanes: `v1.N.1` through `v1.N.10`, then roll to `v1.(N+1).1`. Do not ship `.0` patch releases in those lanes.
- If work naturally breaks into multiple release-sized updates, commit and push them separately in order instead of bundling several release numbers into one large commit.
- If a version gap is discovered after push, backfill the release notes immediately and tighten the repo instructions before continuing with later versions.

## Installation

### Claude Code

```bash
git clone https://github.com/jask04/last24hours-skill.git ~/.claude/skills/last24hours
```

### Codex CLI

```bash
git clone https://github.com/jask04/last24hours-skill.git ~/.agents/skills/last24hours
```

### Gemini CLI

```bash
gemini extensions install https://github.com/jask04/last24hours-skill.git
```

## Configuration

Create `~/.config/last24hours/.env`.

Minimum useful setup:

```bash
AUTH_TOKEN=...
CT0=...
```

The skill also works without any paid Reddit scraper. Reddit public JSON search is enabled by default, and optional official Reddit OAuth credentials improve rate-limit handling and thread/comment enrichment when available.
Set `LAST24HOURS_REDDIT_SOURCE=auto` to prefer OAuth when configured and fall back to public JSON, `oauth` to try OAuth first with a warning on fallback, or `public` to force the no-key path.
`SCRAPECREATORS_API_KEY` is optional and only improves paid Reddit enrichment plus TikTok/Instagram coverage.
Set `LAST24HOURS_DISABLE_SCRAPECREATORS=1` to keep a stored key while skipping ScrapeCreators-backed credit paths.

Bluesky search now tries the public API first. If you have `BSKY_HANDLE` and `BSKY_APP_PASSWORD` configured, they are used as an authenticated fallback instead of being the only path.

Optional:

```bash
SCRAPECREATORS_API_KEY=...
LAST24HOURS_DISABLE_SCRAPECREATORS=1
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=last24hours by u/your_reddit_username
LAST24HOURS_REDDIT_SOURCE=auto
OPENAI_API_KEY=...
XAI_API_KEY=...
BSKY_HANDLE=you.bsky.social
BSKY_APP_PASSWORD=xxxx-xxxx-xxxx
TRUTHSOCIAL_TOKEN=...
BRAVE_API_KEY=...
PARALLEL_API_KEY=...
OPENROUTER_API_KEY=...
```

Kalshi requires no auth for public market-data retrieval in v1.
Polymarket requires no auth for public market discovery in v1.
National Weather Service weather lookup requires no auth for supported U.S. city aliases.

## Usage

```text
/last24hours [topic]
/last24hours [topic] for [tool]
```

Examples:
- `/last24hours Duke vs Houston tonight`
- `/last24hours tomorrows nba games`
- `/last24hours NYC rain tomorrow`
- `/last24hours Fed rate cut probability`
- `/last24hours Trump approval next month`
- `/last24hours Lakers vs Nuggets odds tonight`
- `/last24hours Bitcoin above 100k this week`
- `/last24hours NBA markets to watch today`
- `/last24hours Polymarket markets closing soon`
- `/last24hours live sports games on Polymarket right now`
- `/last24hours macro markets to watch around Fed cuts`
- `/last24hours recommend Polymarket and Kalshi markets around inflation`
- `/last24hours crypto prediction markets to watch today`

Usage guidelines:
- Forecast prompts return one forecast-first answer with `Forecast`, `Market view`, `Why this is the current line`, `Confidence / uncertainty`, and `What changes the number`.
- Market-watchlist prompts return ranked market picks, not one synthesized forecast.
- Closing-soon and live-sports watchlist prompts prioritize near-expiry/live markets over long-dated topic matches.
- Live-sports watchlists return direct matching game-outcome markets only; if ESPN finds no live/starting-soon games or no direct Polymarket match, the output says so directly.
- Narrow watchlist prompts by domain, league, asset, or macro theme when possible.
- Broad prompts such as `markets to watch` degrade to a lower-confidence scan and may return no picks if market matches are weak.
- Watchlist rankings are informational market-monitoring outputs, not trade execution or allocation advice.

Useful CLI flags:
- `--quick`, `--deep`: change source fanout and timeout budget.
- `--emit=compact`, `--emit=json`: choose chat-friendly or machine-readable output.
- `--search=polymarket,kalshi,x,reddit,web`: force a source subset.
- `--as-of-date YYYY-MM-DD`: pin `today`, `tomorrow`, weather target dates, and NBA slate expansion.
- `--closing-window-hours N`: change the closing-soon scan window, default `12`.
- `--live-sports`: force live-game discovery for a watchlist prompt.
- `--paper-watchlist`: record selected watchlist candidates as hypothetical paper picks.
- `--save-dir DIR`: write raw markdown reports and clean old `*-raw*.md` files after the retention window.
- `--save-retention-days N`: change raw-report retention, default `14`.
- `--clean-save-dir --save-dir DIR`: clean saved raw reports without running a forecast.

## Paper Forecast Ledger

The paper ledger is an offline calibration loop for hypothetical picks. It runs a fixed portfolio, stores forecast probabilities and market identities in `~/.local/share/last24hours/paper/` plus the local SQLite store, resolves old picks when public Kalshi or Polymarket outcomes are available, and summarizes calibration drift. NBA game picks can resolve from ESPN public final scores, and NWS-led weather picks can resolve from observed station precipitation after the forecast date has passed.

```bash
python3 scripts/paper.py daily --portfolio fixtures/paper_portfolio.json --quick
python3 scripts/paper.py resolve
python3 scripts/paper.py report --days 30
python3 scripts/paper.py suggest --days 90
python3 scripts/paper.py install-launchd --time 08:00 --dry-run
python3 scripts/paper.py install-launchd --time 08:00 --load
```

Manual resolution is available for outcomes that do not have a deterministic public resolver:

```bash
python3 scripts/paper.py resolve --pick-id ID --outcome 1
python3 scripts/paper.py resolve --pick-id ID --outcome 0
```

The daily macOS runner writes `~/Library/LaunchAgents/com.jask.last24hours.paper-daily.plist` and prints the `launchctl bootstrap` command. It does not load the LaunchAgent unless `--load` is passed. Logs go to `~/.local/share/last24hours/logs/`.

Paper records are intentionally hypothetical. The ledger does not execute trades, size positions, recommend stakes, or mutate forecast weights automatically.

## Local Runs

```bash
python3 scripts/last24hours.py "Duke vs Houston tonight" --quick
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "todays nba games" --quick --emit=compact
python3 scripts/last24hours.py "NBA markets to watch today" --quick --emit=compact
python3 scripts/last24hours.py "NBA games April 20 2026 through April 22 2026" --quick --emit=compact --as-of-date 2026-04-20
python3 scripts/last24hours.py "NBA paper bundle ideas April 20 through April 22" --quick --emit=compact --as-of-date 2026-04-20
python3 scripts/last24hours.py "Polymarket markets closing soon" --quick --emit=compact
python3 scripts/last24hours.py "live sports games on Polymarket right now" --quick --emit=compact --live-sports
python3 scripts/last24hours.py "crypto markets closing soon tonight" --quick --emit=compact --closing-window-hours 6
python3 scripts/last24hours.py "Polymarket markets closing soon" --quick --emit=json --paper-watchlist --closing-window-hours 6
python3 scripts/last24hours.py "NBA paper bundle ideas April 20 through April 22" --quick --emit=json --paper-bundles --as-of-date 2026-04-20
python3 scripts/last24hours.py "NBA matchups tomorrow" --quick --emit=compact --as-of-date 2026-04-19
python3 scripts/last24hours.py "Trail Blazers vs Spurs April 21 2026 Game 2" --quick --emit=compact --as-of-date 2026-04-19
python3 scripts/last24hours.py --diagnose
python3 scripts/last24hours.py "Fed rate cut probability" --search=polymarket,kalshi,x,reddit --emit=compact
```

## Round Testing Convention

After each implementation round, run at least:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q scripts tests
git diff --check
```

Feature smoke tests:

```bash
python3 scripts/last24hours.py "NBA markets to watch today" --quick --emit=compact
python3 scripts/last24hours.py "macro markets to watch around Fed cuts" --quick --emit=compact
python3 scripts/last24hours.py "todays nba games" --quick --emit=compact
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "Boston Celtics at New York Knicks tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "Will the Fed cut rates by June" --quick --emit=compact
python3 scripts/last24hours.py "Will the US have a recession in 2026" --quick --emit=compact
python3 scripts/last24hours.py "Polymarket markets closing soon" --quick --emit=compact --closing-window-hours 6
python3 scripts/last24hours.py "crypto markets closing soon tonight" --quick --emit=compact --closing-window-hours 6
python3 scripts/last24hours.py "live sports games on Polymarket right now" --quick --emit=compact --search=polymarket
python3 scripts/paper.py daily --portfolio fixtures/paper_portfolio.json --quick --dry-run
python3 scripts/paper.py report --days 30
```

Recommended extra smoke tests:
- a market-backed macro/politics query
- a no-market prediction query
- a direct Codex chat invocation using the installed skill path

## Forecasting Behavior

- Forecastable requests default to `prediction` mode.
- Market-watchlist requests such as `markets to watch`, `best markets`, `recommend markets`, `market picks`, `biggest market moves`, `closing soon`, `live markets`, `live games`, and `settling soon` route to `market_watchlist` mode.
- Sports, weather, elections, macro, and event/outcome phrasing map to prediction mode automatically.
- Comparison mode compares probability and market quality, not just sentiment.
- Market evidence outranks social chatter when relevance is similar.
- Social and web evidence are used to explain the line, not replace it.
- For sports, forecast rationale requires high-signal injury, availability, lineup, rest, motivation, or exact-date market-context evidence; generic previews, tickets, betting bots, historical clips, and stale game threads stay out of `Why this is the current line`.
- For weather and macro, low-signal X, Reddit, and web snippets are suppressed aggressively when they do not contain actual domain signal.
- For supported U.S. weather prompts, NWS precipitation probability can anchor the forecast and renders as `NWS-led`.
- Broad NBA slate queries automatically expand into one search per scheduled matchup.
- Broad NBA slate queries league-lock market sections so cross-league city collisions such as MLB markets do not leak into NBA boards.
- Broad NBA slate forecasts require direct game-outcome markets. Player props can appear in watchlist mode only when explicitly labeled as props.

## Market Watchlist Mode

Market-watchlist mode is a one-shot discovery flow inside `scripts/last24hours.py`. It does not use `scripts/watchlist.py`, which remains reserved for persistent topic monitoring.

The ranker combines:
- topic relevance
- exchange-native signal quality
- close time and minutes-to-close for closing-soon scans
- 24h volume, liquidity, and open interest
- bid-ask spread when available
- recent 24h market movement
- fresh catalyst evidence from X, Reddit, web, and Hacker News
- cross-market disagreement when comparable Polymarket and Kalshi contracts exist

Kalshi watchlist candidates are enriched with public batch candlesticks when available to estimate 24h movement, 24h volume, latest open interest, and signal timestamps. For high-value domains such as NBA, Fed/rates, and BTC/ETH, the Kalshi path also checks direct series/event markets so the first page of generic multigame markets does not hide relevant contracts. Polymarket candidates normalize public Gamma market fields such as 24h volume, liquidity, one-day movement, and bid/ask or spread fields when present. Missing enrichment does not drop a market; it is reflected in the market signal and risk note.

Closing-soon scans use Polymarket Gamma `public-search` seeds for daily, today/tomorrow, crypto daily/hourly, weather daily, and live sports matchup terms. They filter closed, inactive, expired, no-liquidity, and effectively settled one-tick markets by default. Live sports discovery uses ESPN public scoreboards for NBA, MLB, NHL, and NFL, searches with full team names, short names, abbreviations, reversed matchups, and league-prefixed aliases, then labels only direct game-outcome markets that match the live or starting-soon matchup.

Watchlist catalyst snippets are market-specific. Crypto candidates require the asset plus crypto/price/flow/macro terms; weather candidates require location plus forecast/weather terms; sports candidates require matchup/team overlap plus injury, lineup, score/clock, delay, pitcher/goalie, or line-movement context. Promo posts, signal-room pitches, picks/parlay chatter, giveaway spam, and domain-mismatched snippets are rejected from catalyst summaries.

When a Kalshi candidate is within range of the watchlist cutoff, the renderer may include it for venue coverage rather than returning an all-Polymarket list. Weak or poorly matched Kalshi rows are still suppressed.

Good prompts:
- `/last24hours NBA markets to watch today`
- `/last24hours Polymarket markets closing soon`
- `/last24hours live sports games on Polymarket right now`
- `/last24hours crypto markets closing soon tonight`
- `/last24hours macro markets to watch this week`
- `/last24hours recommend Polymarket and Kalshi markets around Fed cuts`
- `/last24hours crypto prediction markets to watch today`

Too-broad prompts such as `/last24hours markets to watch` are allowed, but they return a lower-confidence scan and only surface candidates that clear the ranker.

`--paper-watchlist` records the selected watchlist candidate as a hypothetical paper pick for later calibration. It stores closing-soon context in ledger notes and remains opt-in, paper-only tracking.

## Official Weather Support

The skill uses the public National Weather Service API for supported U.S. weather prompts. No API key is required.

Supported built-in aliases include:
- `NYC`, `New York`, `LA`, `Chicago`, `Miami`, `Boston`, `DC`, `Seattle`, `San Francisco`, `Dallas`, `Houston`, `Phoenix`, `Denver`, `Las Vegas`, `Philadelphia`, and `Atlanta`

The weather source captures:
- peak precipitation probability for the requested today/tomorrow window
- short forecast
- temperature
- wind
- NWS source URL and timestamp

If the location is not in the built-in alias map, the skill falls back cleanly to the existing market/model-implied behavior and states that no official weather anchor was available.

## Kalshi Support

Kalshi is a first-class source in this version:
- `--search=kalshi` is supported
- auto mode includes Kalshi for prediction queries
- output includes a dedicated Kalshi section
- context export and source footer include Kalshi

The Kalshi integration captures:
- contract title
- API market URL
- current implied probability
- recent movement when available
- volume
- open interest
- liquidity
- expiration/end date

## Scoring

The skill still uses hour-based recency, but prediction-market scoring now weights:
- semantic relevance
- live market quality
- recent market movement
- volume / liquidity / open interest

For prediction queries, market sources rank above social and web evidence when the topic match is comparable.

## When To Use It

Use `/last24hours` when you want:
- a live probability estimate
- the current market line
- the strongest evidence from the last day
- a quick view of what would move the forecast

Use `/last30days` when you want:
- retrospective research
- longer-term trend summaries
- broad best-practice or prompting research

## Troubleshooting

If you get sparse results:
- try `--days=2`
- try a more outcome-specific phrasing
- use `--search=polymarket,kalshi,x,reddit,web` to force a market-heavy run

If X is not working:
- refresh `AUTH_TOKEN` and `CT0`
- or set `XAI_API_KEY`

If Reddit is sparse or empty:
- public Reddit search is free but can be thinner for niche topics
- `SCRAPECREATORS_API_KEY` is optional if you want better Reddit/TikTok/Instagram coverage
- set `LAST24HOURS_DISABLE_SCRAPECREATORS=1` or pass `--no-scrapecreators` when you want to avoid paid/credit-backed ScrapeCreators calls
- Reddit enrichment in the source footer refers to free `reddit.com/.json` comment/engagement enrichment unless the message explicitly says `ScrapeCreators`

If Bluesky is failing with 403:
- the public Bluesky API may be blocking the request at the network edge
- this does not necessarily mean your app password is wrong
- run `--search=bluesky` or `--search=bsky` to test Bluesky directly; public search runs first, then authenticated fallback uses `BSKY_HANDLE` and `BSKY_APP_PASSWORD`

If YouTube is missing:
- install `yt-dlp`

```bash
pip install yt-dlp
```

## Security

The skill reads public market and social data. It does not place trades, access private exchange data, make bet recommendations, size stakes, or execute orders. Paper picks are hypothetical calibration records only.

Kalshi public market data is retrieved from:
- `https://api.elections.kalshi.com/trade-api/v2`

Polymarket public market data is retrieved from:
- `https://gamma-api.polymarket.com`

National Weather Service public forecast data is retrieved from:
- `https://api.weather.gov`

## License

MIT. See [LICENSE](LICENSE).
