# /last24hours v1.0.8

`/last24hours` is a real-time forecasting and market-watchlist skill. It uses the last 24 hours of market, social, and web evidence to produce a probability forecast first, then explains the evidence and uncertainty behind it. It can also run one-shot topic-scoped market discovery for prompts such as `NBA markets to watch today` or `macro markets to watch around Fed cuts`.

Codex chat is the primary target UX. The compact output is designed to open with a forecast block that feels native in chat, with raw evidence sections following underneath for inspection.

Forecasts are now market-anchored by default. When Polymarket and Kalshi both exist for the same outcome, the skill blends them with liquidity/quality weighting and widens uncertainty when the spread is meaningful.

When no clean market or official source can anchor a forecast, the output now marks the run as degraded so model-implied probabilities are not mistaken for market-backed edges.

Market-watchlist mode is separate from forecasting mode. It ranks Polymarket and Kalshi markets by topic relevance, exchange-native signal quality, 24h volume, liquidity/open interest, bid-ask spread, recent movement, catalyst evidence, and cross-market disagreement. The output is informational market monitoring, not trade execution or allocation advice.

Paper forecast tracking is available for calibration work. The paper ledger records hypothetical daily forecasts, resolves them later when public market outcomes are available, scores calibration, tracks whether the portfolio is leaning on easy favorites or longshots, and prints suggested system improvements for review. New paper records include the skill version so calibration can be compared across forecast-engine changes. It does not place trades, size positions, recommend stakes, or automatically change forecast weights.

For sports, the market sets the number and social/web evidence mainly explains the line. The skill now prefers injuries, lineups, rest, playoff incentives, and meaningful line movement over betting-bot chatter, ticket resale posts, or generic hype.

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

Recent upstream `last30days` v3 ideas are adapted selectively: deterministic search planning, cross-source evidence fusion, small evidence clustering, and per-author caps. These only improve retrieval and explanations; they do not replace the market-anchored forecast engine.

Built on [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn.

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
Why it ranks: market depth, movement, catalyst context, or cross-market signal
Market signal: price, 24h move, spread, 24h volume, liquidity, open interest, and signal-quality notes
Catalyst / evidence: X, Reddit, web, or HN context when it clears quality filters
Risk / what would change it: why the ranking could break or need revision
```

If the request is too broad, the skill returns a lower-confidence watchlist using only high-quality available candidates. If no clean candidates exist, it says `No high-quality market picks found` and lists the filters that failed.

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

Supporting evidence is fused across X, Reddit, web, HN, Bluesky, and Truth Social with source weights, domain quality filters, light clustering, and per-author caps. This selects cleaner drivers for `Why this is the current line` and market-watchlist catalyst notes without letting social evidence move a clean market anchor.

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
- `/last24hours macro markets to watch around Fed cuts`
- `/last24hours recommend Polymarket and Kalshi markets around inflation`
- `/last24hours crypto prediction markets to watch today`

Usage guidelines:
- Forecast prompts return one forecast-first answer with `Forecast`, `Market view`, `Why this is the current line`, `Confidence / uncertainty`, and `What changes the number`.
- Market-watchlist prompts return ranked market picks, not one synthesized forecast.
- Narrow watchlist prompts by domain, league, asset, or macro theme when possible.
- Broad prompts such as `markets to watch` degrade to a lower-confidence scan and may return no picks if market matches are weak.
- Watchlist rankings are informational market-monitoring outputs, not trade execution or allocation advice.

## Paper Forecast Ledger

The paper ledger is an offline calibration loop for hypothetical picks. It runs a fixed portfolio, stores forecast probabilities and market identities in `~/.local/share/last24hours/paper/` plus the local SQLite store, resolves old picks when public Kalshi or Polymarket outcomes are available, and summarizes calibration drift. NBA game picks can resolve from ESPN public final scores, and NWS-led weather picks can resolve from observed station precipitation after the forecast date has passed.

```bash
python3 scripts/paper.py daily --portfolio fixtures/paper_portfolio.json --quick
python3 scripts/paper.py resolve
python3 scripts/paper.py report --days 30
python3 scripts/paper.py suggest --days 90
python3 scripts/paper.py install-launchd --time 08:00 --dry-run
```

Manual resolution is available for outcomes that do not have a deterministic public resolver:

```bash
python3 scripts/paper.py resolve --pick-id ID --outcome 1
python3 scripts/paper.py resolve --pick-id ID --outcome 0
```

The daily macOS runner writes `~/Library/LaunchAgents/com.jask.last24hours.paper-daily.plist` and prints the `launchctl bootstrap` command. It does not load the LaunchAgent unless `--load` is passed.

## Local Runs

```bash
python3 scripts/last24hours.py "Duke vs Houston tonight" --quick
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "todays nba games" --quick --emit=compact
python3 scripts/last24hours.py "NBA markets to watch today" --quick --emit=compact
python3 scripts/last24hours.py --diagnose
python3 scripts/last24hours.py "Fed rate cut probability" --search=polymarket,kalshi,x,reddit --emit=compact
```

## Round Testing Convention

After each implementation round, run at least:

```bash
python3 -c "import py_compile; py_compile.compile('scripts/last24hours.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/render.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/openai_reddit.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/score.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/kalshi.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/forecast.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/weather.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/evidence_quality.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('scripts/lib/market_watchlist.py', doraise=True)"
python3 -m unittest discover -s tests
python3 scripts/last24hours.py "NBA markets to watch today" --quick --emit=compact
python3 scripts/last24hours.py "macro markets to watch around Fed cuts" --quick --emit=compact
python3 scripts/last24hours.py "todays nba games" --quick --emit=compact
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "Boston Celtics at New York Knicks tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "Will the Fed cut rates by June" --quick --emit=compact
python3 scripts/last24hours.py "Will the US have a recession in 2026" --quick --emit=compact
```

Recommended extra smoke tests:
- a market-backed macro/politics query
- a no-market prediction query
- a direct Codex chat invocation using the installed skill path

## Forecasting Behavior

- Forecastable requests default to `prediction` mode.
- Market-watchlist requests such as `markets to watch`, `best markets`, `recommend markets`, `market picks`, and `biggest market moves` route to `market_watchlist` mode.
- Sports, weather, elections, macro, and event/outcome phrasing map to prediction mode automatically.
- Comparison mode compares probability and market quality, not just sentiment.
- Market evidence outranks social chatter when relevance is similar.
- Social and web evidence are used to explain the line, not replace it.
- For sports, low-signal chatter is omitted when there is no clean injury, lineup, rest, or motivation signal.
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
- 24h volume, liquidity, and open interest
- bid-ask spread when available
- recent 24h market movement
- fresh catalyst evidence from X, Reddit, web, and Hacker News
- cross-market disagreement when comparable Polymarket and Kalshi contracts exist

Kalshi watchlist candidates are enriched with public batch candlesticks when available to estimate 24h movement, 24h volume, latest open interest, and signal timestamps. For high-value domains such as NBA, Fed/rates, and BTC/ETH, the Kalshi path also checks direct series/event markets so the first page of generic multigame markets does not hide relevant contracts. Polymarket candidates normalize public Gamma market fields such as 24h volume, liquidity, one-day movement, and bid/ask or spread fields when present. Missing enrichment does not drop a market; it is reflected in the market signal and risk note.

When a Kalshi candidate is within range of the watchlist cutoff, the renderer may include it for venue coverage rather than returning an all-Polymarket list. Weak or poorly matched Kalshi rows are still suppressed.

Good prompts:
- `/last24hours NBA markets to watch today`
- `/last24hours macro markets to watch this week`
- `/last24hours recommend Polymarket and Kalshi markets around Fed cuts`
- `/last24hours crypto prediction markets to watch today`

Too-broad prompts such as `/last24hours markets to watch` are allowed, but they return a lower-confidence scan and only surface candidates that clear the ranker.

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
