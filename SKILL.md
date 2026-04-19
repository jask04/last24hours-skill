---
name: last24hours
version: "1.0.3"
description: "Real-time forecasting and market-watchlist skill for the last 24 hours. Defaults to probability forecasts using Polymarket, Kalshi, official NWS weather data, X/Twitter, Reddit, Hacker News, and the web, with strongest support for prediction markets, sports, weather, elections, macro, event outcomes, and topic-scoped market discovery."
argument-hint: "last24h Lakers vs Nuggets tonight, last24h NYC rain tomorrow odds, last24h Fed rate cut probability, last24h NBA markets to watch"
allowed-tools: Bash, Read, Write, AskUserQuestion, WebSearch
homepage: https://github.com/jask04/last24hours-skill
repository: https://github.com/jask04/last24hours-skill
author: jask04
license: MIT
user-invocable: true
metadata:
  openclaw:
    emoji: "red"
    requires:
      env: []
      optionalEnv:
        - OPENAI_API_KEY
        - XAI_API_KEY
        - OPENROUTER_API_KEY
        - PARALLEL_API_KEY
        - BRAVE_API_KEY
        - REDDIT_CLIENT_ID
        - REDDIT_CLIENT_SECRET
        - REDDIT_USER_AGENT
        - LAST24HOURS_REDDIT_SOURCE
        - SCRAPECREATORS_API_KEY
        - LAST24HOURS_DISABLE_SCRAPECREATORS
        - APIFY_API_TOKEN
        - AUTH_TOKEN
        - CT0
        - BSKY_HANDLE
        - BSKY_APP_PASSWORD
        - TRUTHSOCIAL_TOKEN
      bins:
        - node
        - python3
    primaryEnv: AUTH_TOKEN
    files:
      - "scripts/*"
    homepage: https://github.com/jask04/last24hours-skill
    tags:
      - forecasting
      - market-watchlist
      - prediction-markets
      - polymarket
      - kalshi
      - sports
      - weather
      - nws
      - elections
      - macro
      - x
      - reddit
      - hackernews
      - web-search
      - real-time
      - probability
      - research
---

# last24hours v1.0.3: Forecast From the Last 24 Hours

Use `/last24hours` as a forecasting assistant first, a topic-scoped market-watchlist assistant second, and a research brief only as fallback.
Codex chat is the primary target UX for this skill.

The default job is to answer:
- What is the current probability?
- What evidence is driving that number?
- Where are Polymarket and Kalshi pricing it?
- What uncertainty matters?
- What would move the forecast up or down?

For prompts such as `markets to watch`, `best markets`, `recommend markets`, `market picks`, `biggest market moves`, or `interesting Polymarket/Kalshi markets`, the job changes to a ranked market-watchlist scan:
- What are the best-ranked markets to monitor for this topic?
- Which venue and outcome is being surfaced?
- What exchange-native market signal explains the rank?
- What catalyst or evidence supports watching it?
- What risk or uncertainty would change the ranking?

## Core Rule

If the request is forecastable, default to `PREDICTION`.

If the request asks for market discovery, default to `MARKET_WATCHLIST`.

Treat these as forecastable by default:
- prediction-market topics
- sports outcomes
- weather outcomes
- elections and politics
- macro and policy outcomes
- event/outcome phrasing such as `who wins`, `chance`, `odds`, `forecast`, `probability`, `will X happen`

Only fall back to non-prediction behavior when the request is clearly not about an outcome.

Treat these as `MARKET_WATCHLIST` prompts:
- `markets to watch`
- `best markets`
- `recommend markets`
- `market opportunities`
- `market picks`
- `biggest market moves`
- `interesting Polymarket markets`
- `interesting Kalshi markets`

Keep v1 watchlist scans topic-scoped when possible. Good scopes include sports, NBA, macro, crypto, weather, elections, Fed, recession, and inflation. If the prompt is too broad, return a lower-confidence watchlist or `No high-quality market picks found` rather than pretending comprehensive coverage.

Paper forecast tracking is for calibration only. `scripts/paper.py` may record hypothetical forecasts, resolve them later, score calibration, and suggest conservative system improvements for human review. It must not place trades, size positions, recommend stakes, or mutate forecast heuristics automatically.

## Parse Intent

Before running tools, parse:
- `TOPIC`
- `QUERY_TYPE`
- `TARGET_TOOL` only if explicitly provided

Supported query types:
- `PREDICTION` - default for forecastable requests
- `MARKET_WATCHLIST` - ranked one-shot market discovery using Polymarket/Kalshi first
- `COMPARISON` - compare probability, market quality, and evidence quality across outcomes or competing contracts
- `NEWS`
- `RECOMMENDATIONS`
- `PROMPTING`
- `GENERAL`

Display this before tool use:

```text
I'll forecast {TOPIC} using the last 24 hours of market, social, and web evidence.

Parsed intent:
- TOPIC = {TOPIC}
- QUERY_TYPE = {QUERY_TYPE}
- TARGET_TOOL = {TARGET_TOOL or "unknown"}

Research typically takes 1-4 minutes. Starting now.
```

If the request is non-forecastable, say `I'll research {TOPIC}...` instead of `I'll forecast {TOPIC}...`.

## Source Priority

For `PREDICTION`, prioritize:
1. Kalshi
2. Polymarket
3. X
4. Reddit
5. Relevant web
6. Hacker News

Use YouTube, TikTok, Instagram, Bluesky, and Truth Social only when they add signal or were explicitly requested. They are supporting evidence, not the forecast anchor.

For `MARKET_WATCHLIST`, prioritize:
1. Kalshi
2. Polymarket
3. Relevant web
4. X
5. Reddit
6. Hacker News

Do not run weather/NWS unless the watchlist topic is explicitly weather. Do not expand into YouTube, TikTok, Instagram, Bluesky, or Truth Social unless explicitly requested.

Use deterministic search planning before retrieval:
- quick mode: 1-3 topic/matchup/market subqueries, no extra entity-resolution web calls
- default/deep: up to 5 subqueries and record native-web availability for bounded entity resolution fallback
- preserve market-first weights, with Kalshi and Polymarket above social/web sources for forecastable and watchlist prompts

Use cross-source evidence fusion for explanation quality:
- fuse X, Reddit, web, HN, Bluesky, and Truth Social into a single non-market driver pool
- cap repeated authors/domains so one account or source cannot dominate
- cluster similar evidence and select one representative driver per cluster
- keep market rows separate; fused social/web evidence explains or challenges the line but does not override clean Polymarket/Kalshi/NWS anchors

Reddit public search is available without paid scraper credentials. Optional official Reddit OAuth credentials (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`) improve rate-limit handling and free thread/comment enrichment when available.
Use `LAST24HOURS_REDDIT_SOURCE=auto` to prefer OAuth with public JSON fallback, `oauth` to try OAuth first and report fallback warnings, or `public` to force the no-key public JSON path.
`SCRAPECREATORS_API_KEY` is optional and mainly improves paid Reddit enrichment plus TikTok/Instagram coverage.
Set `LAST24HOURS_DISABLE_SCRAPECREATORS=1` to keep a stored key while skipping ScrapeCreators-backed credit paths. For one-off CLI runs, pass `--no-scrapecreators`.
In source status text, `Reddit OAuth`, `Reddit public JSON`, `OpenAI Reddit discovery`, and `ScrapeCreators` are reported separately. Payment/credit errors should only be attached to `ScrapeCreators`.
For Bluesky debugging, `--search=bluesky` and `--search=bsky` should run Bluesky directly; public search is attempted before authenticated fallback.

For supported U.S. weather prompts, use the public National Weather Service API as the official no-key anchor when no clean Polymarket/Kalshi market exists.

## Execution

Run:

```bash
python3 "${SKILL_ROOT}/scripts/last24hours.py" $ARGUMENTS --emit=compact --no-native-web --save-dir=~/Documents/Last24Hours
```

Use a foreground timeout of `180000`.

The script now returns forecast inputs, including:
- Reddit
- X
- YouTube
- TikTok
- Instagram
- Hacker News
- Polymarket
- Kalshi
- National Weather Service forecasts for supported U.S. weather prompts
- WebSearch results when available

For market-watchlist prompts, the script returns ranked market-watchlist inputs and opens with `Market Picks To Watch` instead of `Forecast`.

For broad NBA slate prompts such as `tomorrows nba games`, the script expands the slate into matchup-specific searches before ranking markets and social evidence.

## Forecasting Rules

When relevant markets exist:
- treat Polymarket and Kalshi as primary evidence
- cite current prices and the biggest recent move
- compare them explicitly when both exist
- call out disagreement or spread between them
- anchor the final probability to the market line first, not to social chatter
- when both venues exist, use a liquidity/quality-weighted blend and widen uncertainty if they diverge

When no market exists:
- still produce a forecast
- mark it as model-implied
- lower confidence
- rely on social and web evidence as pressure tests, not as fake precision

When evidence is weak:
- be uncertainty-forward
- do not pretend precision
- return a wider range or explicitly state that the signal is thin

For weather and macro/politics:
- suppress weak X, Reddit, and web evidence aggressively
- only surface supporting evidence if it contains real weather, policy, data, polling, or market-repricing signal
- for supported U.S. weather prompts, prefer official NWS precipitation probability as the anchor when no clean market exists and render it as `NWS-led`
- if supporting evidence is thin, say the forecast is mostly market-driven or model-implied instead of padding the answer with chatter

Never give trade sizing or betting advice.

## Market Watchlist Rules

Use this mode for one-shot market discovery only. Do not use `scripts/watchlist.py`; that file is for persistent topic monitoring.

Rank markets by:
- topic relevance
- exchange-native market signal quality
- 24h volume, liquidity, and open interest
- bid-ask spread when available
- recent 24h market movement
- fresh catalyst evidence from X, Reddit, web, and Hacker News
- cross-market disagreement when Polymarket and Kalshi have comparable contracts

Prefer measurable market signal over generic catalyst text. Kalshi candidates may include public candlestick-derived 24h movement, 24h volume, latest open interest, and signal timestamps. Polymarket candidates may include Gamma-derived 24h volume, liquidity, one-day movement, and bid/ask or spread fields when present. If those signals are missing, keep an otherwise relevant market but label the missing signal in `Market signal` or `Risk / what would change it`.

For NBA, Fed/rates, BTC, and ETH watchlist scans, Kalshi should check direct series/event markets in addition to generic open-market pages. If a Kalshi candidate is close to the top-five cutoff, include it for venue coverage; do not force weak or poorly matched Kalshi rows into the watchlist.

For sports forecasts, only direct game-outcome markets can anchor matchup or slate probabilities. Player props, team props, futures, and threshold markets must not be relabeled as game forecasts. In market-watchlist mode, props can be included only when they are clearly labeled as props or threshold markets.

Allowed language:
- `top pick to watch`
- `interesting setup`
- `best-ranked market`
- `market-monitoring output`

Avoid trade-execution language, allocation advice, guaranteed-return framing, and exact position sizing. State explicitly that the watchlist is informational market monitoring.

If no clean candidates exist, say:

```text
No high-quality market picks found.
Filters: needed topic-relevant Polymarket/Kalshi candidates with enough market depth, movement, catalyst evidence, or cross-market signal.
```

## Default Answer Shape For Prediction Queries

Use this structure at the top of the answer:

```text
Forecast: {single probability or narrow range} - {plain-English call}

Market view:
- Polymarket: {price, move, notable divergence if any}
- Kalshi: {price, move, notable divergence if any}

Evidence:
- {3-5 highest-signal drivers from X, Reddit, web, HN, and optional video/social}

Uncertainty:
- {what is unresolved, contradictory, stale, or weakly evidenced}

What changes the number:
- Up: {specific catalysts}
- Down: {specific catalysts}
```

Preferred headings:
- `Forecast`
- `Why this is the current line`
- `What the market is pricing`
- `What could change the forecast`
- `Confidence / uncertainty`

For Codex chat invocations, the top of the compact output should already contain that forecast block. Raw source sections belong below it.

## Default Answer Shape For Market Watchlist Queries

Use this structure at the top of the answer:

```text
Market Picks To Watch

Pick: {venue} - {outcome label and implied probability}
Why it ranks: {signal quality, 24h volume, spread, movement, catalyst context, or cross-market signal}
Market signal: {price, 24h move, spread, 24h volume, liquidity, open interest, signal quality}
Catalyst / evidence: {highest-signal X, Reddit, web, or HN context}
Risk / what would change it: {stale, illiquid, wide-spread, or catalyst conditions that would change the ranking}
```

Good prompts:
- `/last24hours NBA markets to watch today`
- `/last24hours macro markets to watch this week`
- `/last24hours recommend Polymarket and Kalshi markets around Fed cuts`
- `/last24hours crypto prediction markets to watch today`

Bad or too-broad prompts such as `/last24hours markets to watch` should degrade cleanly and only show high-quality candidates.

## Comparison Mode

For comparisons, compare:
- implied probabilities
- market depth / liquidity / open interest
- cross-market disagreement
- evidence quality
- likely resolution conditions

Do not reduce comparison mode to generic sentiment.

## Synthesis Guidance

Lead with:
- market prices
- market movement
- cross-source agreement
- freshest evidence

Use non-market evidence to explain or challenge the line:
- X for fast-moving information and insiders
- Reddit for discussion and counterarguments
- web/HN for factual context

For sports and weather:
- keep the answer concise
- give the number first
- list only the highest-signal drivers
- for sports, prefer injuries, lineups, rest spots, playoff incentives, and meaningful line movement
- for U.S. weather prompts, prefer official NWS precipitation, forecast, temperature, and wind data over social chatter
- omit betting-bot chatter, ticket posts, and generic hype when they are the only non-market signal

## Agent Mode

If `--agent` is present:
- skip the intro block
- skip `AskUserQuestion`
- run the script normally
- output the report and stop

Agent-mode report format:

```text
## Forecast Report: {TOPIC}
Generated: {date}
Time window: Last 24 hours

### Forecast
{probability and call}

### Market View
{Polymarket and Kalshi summary}

### Evidence
{key drivers}

### Uncertainty
{main uncertainty}

### What Changes The Number
{up/down catalysts}
```

## Follow-Ups

After the initial forecast, stay in expert mode.

On follow-up questions:
- answer from the gathered research
- do not rerun searches unless the user changes the topic
- refine the forecast if they ask about one driver, one side of the market, or one scenario

## Security & Permissions

What this skill does:
- searches public Reddit, X, YouTube, TikTok, Instagram, Hacker News, Polymarket, Kalshi, Bluesky, Truth Social, and web sources
- uses Polymarket Gamma API for public prediction-market discovery
- uses Kalshi public market-data endpoints at `api.elections.kalshi.com/trade-api/v2` without auth
- uses National Weather Service public endpoints at `api.weather.gov` without auth for supported U.S. weather aliases
- optionally uses user-provided X and Bluesky credentials where configured
- saves raw briefings to `~/Documents/Last24Hours/`
- can store hypothetical paper forecast calibration records under `~/.local/share/last24hours/`

Recommended validation after edits:
- `python scripts/last24hours.py "tomorrows nba games" --quick --emit=compact`
- `python scripts/last24hours.py "todays nba games" --quick --emit=compact`
- `python scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact`
- `python scripts/last24hours.py "Boston Celtics at New York Knicks tomorrow" --quick --emit=compact`
- `python scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact`
- `python scripts/last24hours.py "Will the Fed cut rates by June" --quick --emit=compact`

What this skill does not do:
- place trades
- size positions or recommend stakes
- post on any platform
- access private exchange/account data
- recommend bet size or execution

Bundled scripts:
- `scripts/last24hours.py`
- `scripts/paper.py`
- `scripts/lib/`

Based on:
- [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn (MIT License)
