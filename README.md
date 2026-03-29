# /last24hours v1.0.0

### Claude Code
```bash
git clone https://github.com/jask04/last24hours-skill.git ~/.claude/skills/last24hours
```

**The news cycle moves in hours, not days.** /last24hours researches your topic across Reddit, X, Bluesky, YouTube, TikTok, Instagram, Hacker News, Polymarket, Truth Social, and the web from the **last 24 hours**, finds what the community is actually upvoting, sharing, betting on, and saying on camera **right now**, and writes you a grounded narrative with real citations. When you need to know what happened *today* — not this month — this is the tool.

**Built on [last30days](https://github.com/mvanhorn/last30days-skill)** by Matt Van Horn (MIT License). Where /last30days gives you a comprehensive 30-day retrospective, /last24hours is laser-focused on breaking news, trending discussions, and real-time community sentiment from the last 24-48 hours.

**Key differences from last30days:**

- **Hour-based recency scoring** — items from 2 hours ago score 95/100, items from 20 hours ago score 58/100, anything older than 48 hours scores 0. The original uses day-based scoring where everything within 24 hours gets the same score.
- **Recency-first weighting** — 40% recency, 30% relevance, 30% engagement (vs 25/45/30 in last30days). For breaking research, *when* something was said matters more than keyword match.
- **X/Twitter and HN prioritized** — X is the fastest-updating platform; Hacker News catches tech breaking news first. Both are promoted in source tiers and tiebreakers. YouTube is demoted since videos take time to produce.
- **Faster timeouts** — ~65% of original values. Less data in a 24h window means faster results (typically 30s-2 minutes).
- **Fresher cache** — 12-hour TTL (vs 24h). Stale cache is worse when you need real-time research.
- **Hard 1-2 day ceiling** — `--days` defaults to 1 and maxes at 2. No scope creep back toward a 30-day tool.

**The tradeoff:** /last24hours finds less content than /last30days (there's only 24 hours of data), but what it finds is maximally fresh. Use /last30days for comprehensive retrospectives, use /last24hours for "what's happening right now?"

## Installation

### Manual Install (Claude Code)
```bash
# Clone the repo
git clone https://github.com/jask04/last24hours-skill.git ~/.claude/skills/last24hours

# Add your API keys
mkdir -p ~/.config/last24hours
cat > ~/.config/last24hours/.env << 'EOF'
SCRAPECREATORS_API_KEY=... # Reddit + TikTok + Instagram (one key, all three) - scrapecreators.com
OPENAI_API_KEY=sk-...      # optional - legacy Reddit fallback
AUTH_TOKEN=...             # recommended for X search - copy once from x.com cookies
CT0=...                    # recommended for X search - copy once from x.com cookies
XAI_API_KEY=xai-...        # optional - X fallback if you do not want cookie-based auth
BSKY_HANDLE=you.bsky.social       # optional - Bluesky search
BSKY_APP_PASSWORD=xxxx-xxxx-xxxx  # optional - bsky.app/settings/app-passwords
EOF
chmod 600 ~/.config/last24hours/.env
```

For project-specific overrides, create `.claude/last24hours.env` in the repo root. It overrides the global `~/.config/last24hours/.env`.

### Gemini CLI
```bash
gemini extensions install https://github.com/jask04/last24hours-skill.git
```

### Codex CLI
```bash
git clone https://github.com/jask04/last24hours-skill.git ~/.agents/skills/last24hours
```

### Already have last30days installed?

If you already have API keys configured for /last30days, just copy them:

```bash
cp ~/.config/last30days/.env ~/.config/last24hours/.env
```

Same keys, same providers — the skills share the same research engine.

### X Search Authentication

X search prefers explicit env auth. This keeps local runs headless and avoids browser-cookie and macOS Keychain prompts.

**Recommended setup:**
1. While logged into x.com once, open browser dev tools and copy the `auth_token` and `ct0` cookies for `x.com`.
2. Save them as `AUTH_TOKEN` and `CT0` in `~/.config/last24hours/.env`, export them in your shell, or add them to `.claude/last24hours.env` for a single project.
3. Run `/last24hours`.

**xAI fallback:** If you do not want to provide `AUTH_TOKEN` and `CT0`, set `XAI_API_KEY` and the skill will use xAI's `x_search` backend instead.

**Verify it's working:**
```bash
node ~/.claude/skills/last24hours/scripts/lib/vendor/bird-search/bird-search.mjs --whoami
```

**Requirements:** Node.js 22+ (for the vendored Twitter GraphQL client).

## Usage

```
/last24hours [topic]
/last24hours [topic] for [tool]
```

Examples:
- `/last24hours AI regulations` — what happened today in AI policy
- `/last24hours Tesla stock` — breaking market sentiment and Polymarket odds
- `/last24hours NBA predictions tonight` — what fans and bettors are saying before tip-off
- `/last24hours OpenAI vs Anthropic` — side-by-side comparison from today's discussions
- `/last24hours severe weather midwest` — latest storm tracking and community reports

## What It Does

1. **Researches** — scans Reddit, X, Bluesky, Truth Social, YouTube, TikTok, Instagram, Hacker News, Polymarket, and the web for discussions from the **last 24 hours**
2. **Scores by freshness** — items posted 2 hours ago rank far higher than items from 20 hours ago, using hour-granularity recency scoring
3. **Synthesizes** — identifies breaking patterns, trending topics, and what the community is saying right now
4. **Delivers** — a grounded, cited expert briefing with hours-ago timestamps ("2h ago", "14h ago") showing exactly when each insight dropped

### Best for:
- **Breaking news** — "What just happened with [topic]?"
- **Trending discussions** — "What are people saying about [topic] today?"
- **Real-time sentiment** — "How is the community reacting to [announcement]?"
- **Market moves** — "What's happening with [stock/crypto] right now?"
- **Prediction markets** — "What are Polymarket odds showing today?"
- **Sports predictions** — "What are fans betting on for tonight's game?"
- **Weather events** — "What's the latest on the incoming storm?"
- **Product launches** — "What are first impressions of [new product]?" (day 1-2)

---

## Example: Breaking AI News

**Query:** `/last24hours Claude Code`

**What you get:**

The skill searches all 10+ sources with a 24-hour window, scores results by how many hours ago they were posted, and synthesizes:

```
What I learned (last 24 hours):

**New skill ecosystem explosion** — SkillsMP hit 87K+ skills, Remotion skill got 17K likes
on X, per @Remotion (3h ago)

**Review loop pattern emerging** — developers combining Claude Code + Codex via MCP for
automated code review, per r/ClaudeCode (6h ago)

**Plugin marketplace launch** — /plugin marketplace command now live, community sharing
install one-liners, per @joshua_xu_ (12h ago)

KEY PATTERNS from the last 24 hours:
1. Skills > CLAUDE.md for "context on demand" — per r/ClaudeCode
2. Remotion for video generation is the viral use case — per @Remotion
3. MCP integration with other AI tools is the power-user workflow — per r/ClaudeAI
```

```
---
✅ All agents reported back! (last 24 hours)
├─ 🟠 Reddit: 4 threads │ 238 upvotes │ 156 comments
├─ 🔵 X: 15 posts │ 28,000 likes │ 2,800 reposts
├─ 🟡 HN: 2 stories │ 48 points │ 31 comments
├─ 🌐 Web: 5 pages — Hacker News, TechCrunch, The Verge
└─ 🗣️ Top voices: @Remotion (17K likes), @joshua_xu_ │ r/ClaudeCode, r/ClaudeAI
---
```

---

## Example: Real-Time Market Sentiment

**Query:** `/last24hours Tesla stock`

The skill surfaces what X, Reddit, and Polymarket are saying *today* — not a 30-day retrospective:

- Breaking X posts from financial accounts with engagement velocity (likes/hour)
- Reddit threads from r/wallstreetbets, r/stocks, r/teslamotors posted in the last 24h
- Polymarket odds with **24-hour movement** ("up 5% today", "dropped 8% since yesterday")
- Hacker News discussion on any related tech announcements

---

## Example: Product Launch First Impressions

**Query:** `/last24hours Seedance 2.0`

When a product launches, /last24hours catches the first wave of reactions:

- X creators posting first impressions within hours of launch
- Reddit threads with early user experiences
- YouTube quick takes (if any live streams or reaction videos)
- Web coverage from tech blogs

The hour-based scoring ensures the freshest reactions rank highest — a post from 3 hours ago with 50 likes outranks a post from 20 hours ago with 200 likes.

---

## Example: Comparative Research

**Query:** `/last24hours Cursor vs Windsurf`

Runs THREE parallel research passes (Cursor alone, Windsurf alone, "Cursor vs Windsurf" combined), then synthesizes a side-by-side comparison:

```
# Cursor vs Windsurf: What the Community Says (Last 24 Hours)

## Quick Verdict
[Data-driven summary with source counts]

## Cursor
**Community Sentiment:** [Positive/Mixed/Negative]
**Strengths** — [with citations]
**Weaknesses** — [with citations]

## Windsurf
**Community Sentiment:** [Positive/Mixed/Negative]
**Strengths** — [with citations]
**Weaknesses** — [with citations]

## Head-to-Head
| Dimension | Cursor | Windsurf |
|-----------|--------|----------|
| ...       | ...    | ...      |

## The Bottom Line
Choose Cursor if... Choose Windsurf if...
```

---

## How It Works

### Hour-Based Recency Scoring

The core innovation over last30days. Instead of day-granularity scoring (where everything within 24 hours gets the same score), last24hours scores by **hours**:

| Age | Recency Score |
|-----|---------------|
| 0-6 hours | 90-100 (bonus zone) |
| 12 hours | 75 |
| 24 hours | 50 |
| 36 hours | 25 |
| 48+ hours | 0 (filtered out) |

Items under 6 hours old get a bonus bump to at least 90/100, ensuring the freshest content always surfaces first.

### Scoring Weights

| Factor | last24hours | last30days |
|--------|-------------|------------|
| Recency | **40%** | 25% |
| Relevance | 30% | 45% |
| Engagement | 30% | 30% |

For breaking research, *when* something was said is the most important signal.

### Source Priority (Default Tiebreaker)

When items have equal scores, sources are prioritized for real-time relevance:

1. **X/Twitter** — fastest-updating, breaking news first
2. **Reddit** — discussion threads form fast, engagement signals
3. **Hacker News** — tech breaking news, developer community
4. **Web** — news articles, blogs
5. **Bluesky** — growing social signal
6. **Truth Social** — political signal
7. **Polymarket** — prediction market odds
8. **YouTube** — videos take time to produce (demoted)
9. **TikTok** — short-form content cycles slower
10. **Instagram** — creator content cycles slower

### Two-Phase Search Architecture

**Phase 1: Broad discovery**
- ScrapeCreators API for Reddit search, subreddit discovery, and comment enrichment
- Vendored Twitter GraphQL search (or xAI API fallback) for X search
- YouTube search + transcript extraction via yt-dlp (when installed)
- Hacker News search via Algolia API (free, no auth)
- Polymarket prediction market search via Gamma API (free, no auth)
- Bluesky search via AT Protocol (optional)
- Truth Social search (optional)
- TikTok and Instagram via ScrapeCreators (optional)
- WebSearch for blogs, news, docs, tutorials
- Reddit JSON enrichment for real engagement metrics
- **Hour-based scoring** weighing recency (40%), relevance (30%), and engagement (30%)

**Phase 2: Smart supplemental search**
- Extracts entities from Phase 1: @handles from X, subreddit names from Reddit
- Runs targeted follow-up searches: `from:@handle topic` on X, subreddit-scoped on Reddit
- Merges and deduplicates with Phase 1 results
- Skipped on `--quick` for speed; extended on `--deep`

### Timeout Profiles

Reduced from last30days since less data = faster results:

| Profile | Global Timeout | Typical Duration |
|---------|---------------|-----------------|
| `--quick` | 60s | 15-30s |
| default | 120s | 30s-2min |
| `--deep` | 200s | 1-3min |

---

## Options

| Flag | Description |
|------|-------------|
| `--days=N` | Look back N days (1-2, default: 1) |
| `--quick` | Faster research, fewer sources (8-12 each) |
| `--deep` | Comprehensive research (50-70 Reddit, 40-60 X) |
| `--debug` | Verbose logging for troubleshooting |
| `--sources=reddit` | Reddit only |
| `--sources=x` | X only |
| `--search=reddit,x,hn` | Pick specific sources (comma-separated) |
| `--include-web` | Add native web search alongside Reddit/X |
| `--diagnose` | Show source availability diagnostics and exit |
| `--save-dir=DIR` | Save briefing to a directory (default: ~/Documents/Last24Hours/) |

## Requirements

- **Python 3** — main research engine
- **Node.js 22+** — for X search (bundled Twitter GraphQL client)
- **At least one API key:**
  - `SCRAPECREATORS_API_KEY` — Reddit + TikTok + Instagram (one key, all three) via [scrapecreators.com](https://scrapecreators.com)
  - `OPENAI_API_KEY` — legacy Reddit fallback
- **Optional for X search:**
  - `AUTH_TOKEN` + `CT0` — X browser cookies (recommended)
  - `XAI_API_KEY` — xAI fallback
- **Optional for other sources:**
  - `BSKY_HANDLE` + `BSKY_APP_PASSWORD` — Bluesky
  - `TRUTHSOCIAL_TOKEN` — Truth Social
  - `BRAVE_API_KEY` / `PARALLEL_API_KEY` / `OPENROUTER_API_KEY` — web search backends
- **Optional:**
  - `yt-dlp` — YouTube search + transcript extraction (`pip install yt-dlp`)

Check source availability: `python3 scripts/last24hours.py --diagnose`

## Troubleshooting

### macOS: SSL Certificate Verify Failed

If you see `[SSL: CERTIFICATE_VERIFY_FAILED]`, your Python installation is missing SSL root certificates. This only affects Python installed from python.org — Homebrew users are not affected.

```bash
# Fix: run the certificate installer (adjust version as needed)
sudo "/Applications/Python 3.12/Install Certificates.command"
```

### No results for a topic

The 24-hour window is narrow. If a topic hasn't been discussed in the last 24 hours, you'll get fewer (or zero) results. Try:
- `--days=2` to extend to 48 hours
- `/last30days` for a broader retrospective

### X search not working

Verify your X auth is configured:
```bash
node ~/.claude/skills/last24hours/scripts/lib/vendor/bird-search/bird-search.mjs --whoami
```

If that fails, either update your `AUTH_TOKEN`/`CT0` cookies or set `XAI_API_KEY` as a fallback.

---

## Security & Privacy

### Data that leaves your machine

| Destination | Data Sent | API Key Required |
|------------|-----------|-----------------|
| `api.scrapecreators.com` | Search query (Reddit + TikTok + Instagram) | SCRAPECREATORS_API_KEY |
| `api.openai.com` | Search query (legacy Reddit fallback) | OPENAI_API_KEY |
| `reddit.com` | Thread URLs for enrichment | None (public JSON) |
| Twitter GraphQL / `api.x.ai` | Search query | AUTH_TOKEN/CT0 or XAI_API_KEY |
| `youtube.com` (via yt-dlp) | Search query | None (public search) |
| `hn.algolia.com` | Search query | None (public API) |
| `gamma-api.polymarket.com` | Search query | None (public API) |
| `api.search.brave.com` | Search query (optional) | BRAVE_API_KEY |
| `api.parallel.ai` | Search query (optional) | PARALLEL_API_KEY |
| `openrouter.ai` | Search query (optional) | OPENROUTER_API_KEY |

Your research topic is included in all outbound API requests. If you research sensitive topics, be aware that query strings are transmitted to the API providers listed above.

### Data stored locally

- API keys: `~/.config/last24hours/.env` (chmod 600 recommended)
- Research briefings: `~/Documents/Last24Hours/` (auto-saved .md files)
- Cache: `~/.cache/last24hours/` (12-hour TTL)

### API key isolation

Each API key is transmitted only to its respective endpoint. Your OpenAI key is never sent to xAI, Brave, or any other provider. Browser cookies for X are read locally and used only for Twitter GraphQL requests.

---

## When to Use last24hours vs last30days

| Use Case | last24hours | last30days |
|----------|-------------|------------|
| "What happened today?" | **Yes** | Overkill |
| "What's trending right now?" | **Yes** | Too much noise |
| "Breaking news on [topic]" | **Yes** | Too slow |
| "Tonight's NBA predictions" | **Yes** | No |
| "Prediction market odds today" | **Yes** | No |
| "Storm tracking / weather updates" | **Yes** | No |
| "Product launch first impressions" | **Yes** (day 1-2) | **Yes** (after a week) |
| "Best practices for [tool]" | No | **Yes** |
| "Comprehensive market research" | No | **Yes** |
| "What prompting techniques work?" | No | **Yes** |

**Rule of thumb:** If you'd check Twitter for it, use /last24hours. If you'd check a blog roundup, use /last30days.

---

## Attribution

This project is a derivative of [last30days](https://github.com/mvanhorn/last30days-skill) by [Matt Van Horn](https://github.com/mvanhorn), licensed under the MIT License. The core research engine, multi-source architecture, and scoring pipeline originate from that project. /last24hours adds hour-based recency scoring, reweighted scoring factors, reduced timeouts, and a SKILL.md rewritten for 24-hour focused research.

## License

MIT — see [LICENSE](LICENSE) for details.

---

*24 hours of breaking intel. 30 seconds of work. Ten sources. Zero stale takes.*

*Built by [Jaskaran Singh](https://github.com/jask04). Based on [last30days](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn.*
