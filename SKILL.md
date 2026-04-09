---
name: last24hours
version: "1.0.0"
description: "Real-time forecasting skill for the last 24 hours. Defaults to probability forecasts using Polymarket, Kalshi, X/Twitter, Reddit, Hacker News, and the web, with strongest support for prediction markets, sports, weather, elections, macro, and event outcomes."
argument-hint: "last24h Lakers vs Nuggets tonight, last24h NYC rain tomorrow odds, last24h Fed rate cut probability"
allowed-tools: Bash, Read, Write, AskUserQuestion, WebSearch
homepage: https://github.com/jask04/last24hours-skill
repository: https://github.com/jask04/last24hours-skill
author: jask04
license: MIT
user-invocable: true
metadata:
  openclaw:
    emoji: "🔴"
    requires:
      env: []
      optionalEnv:
        - OPENAI_API_KEY
        - XAI_API_KEY
        - OPENROUTER_API_KEY
        - PARALLEL_API_KEY
        - BRAVE_API_KEY
        - SCRAPECREATORS_API_KEY
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
      - prediction-markets
      - polymarket
      - kalshi
      - sports
      - weather
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

# last24hours v1.0.0: Forecast From the Last 24 Hours

Use `/last24hours` as a forecasting assistant first and a research brief second.
Codex chat is the primary target UX for this skill.

The default job is to answer:
- What is the current probability?
- What evidence is driving that number?
- Where are Polymarket and Kalshi pricing it?
- What uncertainty matters?
- What would move the forecast up or down?

## Core Rule

If the request is forecastable, default to `PREDICTION`.

Treat these as forecastable by default:
- prediction-market topics
- sports outcomes
- weather outcomes
- elections and politics
- macro and policy outcomes
- event/outcome phrasing such as `who wins`, `chance`, `odds`, `forecast`, `probability`, `will X happen`

Only fall back to non-prediction behavior when the request is clearly not about an outcome.

## Parse Intent

Before running tools, parse:
- `TOPIC`
- `QUERY_TYPE`
- `TARGET_TOOL` only if explicitly provided

Supported query types:
- `PREDICTION` — default for forecastable requests
- `COMPARISON` — compare probability, market quality, and evidence quality across outcomes or competing contracts
- `NEWS`
- `RECOMMENDATIONS`
- `PROMPTING`
- `GENERAL`

Display this before tool use:

```text
I’ll forecast {TOPIC} using the last 24 hours of market, social, and web evidence.

Parsed intent:
- TOPIC = {TOPIC}
- QUERY_TYPE = {QUERY_TYPE}
- TARGET_TOOL = {TARGET_TOOL or "unknown"}

Research typically takes 1-4 minutes. Starting now.
```

If the request is non-forecastable, say `I’ll research {TOPIC}...` instead of `I’ll forecast {TOPIC}...`.

## Source Priority

For `PREDICTION`, prioritize:
1. Kalshi
2. Polymarket
3. X
4. Reddit
5. Relevant web
6. Hacker News

Use YouTube, TikTok, Instagram, Bluesky, and Truth Social only when they add signal or were explicitly requested. They are supporting evidence, not the forecast anchor.

Reddit public search is available without paid scraper credentials. `SCRAPECREATORS_API_KEY` is optional and mainly improves Reddit comment enrichment plus TikTok/Instagram coverage.

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
- WebSearch results when available

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

Never give trade sizing or betting advice.

## Default Answer Shape For Prediction Queries

Use this structure at the top of the answer:

```text
Forecast: {single probability or narrow range} — {plain-English call}

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
- optionally uses user-provided X and Bluesky credentials where configured
- saves raw briefings to `~/Documents/Last24Hours/`

Recommended validation after edits:
- `python scripts/last24hours.py "tomorrows nba games" --quick --emit=compact`
- `python scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact`
- `python scripts/last24hours.py "Boston Celtics at New York Knicks tomorrow" --quick --emit=compact`
- `python scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact`

What this skill does not do:
- place trades
- post on any platform
- access private exchange/account data
- recommend bet size or execution

Bundled scripts:
- `scripts/last24hours.py`
- `scripts/lib/`

Based on:
- [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn (MIT License)
