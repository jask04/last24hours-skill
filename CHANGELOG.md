# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
