# /last24hours v1.0.0

`/last24hours` is a real-time forecasting skill. It uses the last 24 hours of market, social, and web evidence to produce a probability forecast first, then explains the evidence and uncertainty behind it.

Codex chat is the primary target UX. The compact output is designed to open with a forecast block that feels native in chat, with raw evidence sections following underneath for inspection.

The skill is optimized for:
- prediction markets
- sports outcomes
- weather outcomes
- elections and politics
- macro and event-driven forecasts

Polymarket and Kalshi are the primary market anchors. X, Reddit, Hacker News, and the web are supporting inputs used to explain, pressure-test, or challenge the market line.

For broad NBA slate prompts such as `tomorrows nba games`, the compact output now opens with a per-game slate forecast board before the raw evidence sections.

Built on [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn.

## What It Returns

For forecastable queries, the default answer shape is:

```text
Forecast: 62-66% — slight lean to yes

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

## Source Priority

For prediction queries:
1. Kalshi
2. Polymarket
3. X
4. Reddit
5. Relevant web
6. Hacker News

YouTube, TikTok, Instagram, Bluesky, and Truth Social are supporting sources unless explicitly requested.

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

The skill also works without any paid Reddit scraper. Reddit public JSON search is enabled by default; `SCRAPECREATORS_API_KEY` is optional and only improves coverage/comment enrichment.

Bluesky search now tries the public API first. If you have `BSKY_HANDLE` and `BSKY_APP_PASSWORD` configured, they are used as an authenticated fallback instead of being the only path.

Optional:

```bash
SCRAPECREATORS_API_KEY=...
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

## Local Runs

```bash
python3 scripts/last24hours.py "Duke vs Houston tonight" --quick
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
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
python3 scripts/last24hours.py "tomorrows nba games" --quick --emit=compact
python3 scripts/last24hours.py "Los Angeles Lakers at Golden State Warriors tomorrow" --quick --emit=compact
python3 scripts/last24hours.py "NYC rain tomorrow" --quick --emit=compact
```

Recommended extra smoke tests:
- a market-backed macro/politics query
- a no-market prediction query
- a direct Codex chat invocation using the installed skill path

## Forecasting Behavior

- Forecastable requests default to `prediction` mode.
- Sports, weather, elections, macro, and event/outcome phrasing map to prediction mode automatically.
- Comparison mode compares probability and market quality, not just sentiment.
- Market evidence outranks social chatter when relevance is similar.
- Social and web evidence are used to explain the line, not replace it.
- Broad NBA slate queries automatically expand into one search per scheduled matchup.

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

If Bluesky is failing with 403:
- the public Bluesky API may be blocking the request at the network edge
- this does not necessarily mean your app password is wrong

If YouTube is missing:
- install `yt-dlp`

```bash
pip install yt-dlp
```

## Security

The skill reads public market and social data. It does not place trades, access private exchange data, or make bet recommendations.

Kalshi public market data is retrieved from:
- `https://api.elections.kalshi.com/trade-api/v2`

Polymarket public market data is retrieved from:
- `https://gamma-api.polymarket.com`

## License

MIT. See [LICENSE](LICENSE).
