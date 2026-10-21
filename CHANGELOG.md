# Changelog

All notable changes to the site, the data format and the classifier rules.
Dates are UTC. Data format changes also appear on `/data/`.

## 2026-10-21 — initial build (unreleased)

### Site
- GSoC organization explorer 2016–2026 (518 organizations after merging renames), org pages with official links, year pages with official vs dataset counts.
- Program calendar with ICS feeds (all programs and per program), with per-entry verification status.
- "Start now for GSoC 2027" guide, Outreachy December 2026 page, opt-out page, about, privacy, methodology, data/API pages.
- Issue finder with URL-state filters and an evidence drawer (renders once the pipeline has run).

### Pipeline
- Discovery via GitHub Search (`advanced_search=true`), qualifiers verified live on 2026-10-21 (see `docs/VERIFIED_QUALIFIERS.md`).
- GraphQL enrichment, claimability classifier v1 (rules on `/methodology`), AI-policy detection, health metrics, daily snapshots to the `data` branch.
- Blind-evaluation harness in `eval/`; verdicts labelled "unverified" until the bar is met.

### Classifier rules
- v1: claimed / stale_claim (14 days) / open / restricted. Patterns listed on `/methodology`.
