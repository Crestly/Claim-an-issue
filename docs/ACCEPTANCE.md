# Acceptance tests — results as measured on 2026-10-21

Each phase in `PLAN.md` has acceptance tests. This file records what was actually measured, by whom (the build agent, locally, Windows 11, Node 22.2, Python 3.12), and what was not.

## Phase 1 — GSoC explorer, calendar, guide

| Test | Result | Notes |
|---|---|---|
| Spot-check 25 random organizations against the source dataset and their official link | **24/25 years match** exactly; 1 "mismatch" (Shogun) was a name-only comparison artefact: our record correctly merges "Shogun Machine Learning Toolbox" (2016–17), "shogun.ml" (2019) and "Shogun" (2020) by homepage. Homepage links: 23/25 HTTP 200, 2 failed from this machine (`fz-juelich.de/en`, `shogun.ml`, both `URLError`; likely TLS/geo quirks, not re-verified in a browser). | Sample seed 20261021; rows in `docs/SPOTCHECK-2026-10-21.csv`. This checks our merge and link fields against the community dataset, **not** against summerofcode.withgoogle.com (we do not scrape it). Official per-year org counts are compared on each `/gsoc/years/{year}/` page. |
| Bug found by the spot-check | Aliases were lost when a curated alias rewrote the name before merging (112 orgs now carry aliases, was 89). Fixed in `pipeline/build_orgs.py`. | |
| Every program entry has an official link and a last-verified date | **6/6 programs, 28/28 events** have `official_url`, `last_verified` and a per-event `status` (verified / from-brief / expected / unverified). | Statuses are rendered on `/calendar/` and prefixed in the ICS. |
| ICS feed validates | Opened by Python's parser and structurally checked (VCALENDAR/VEVENT, CRLF, 75-octet folding, DTEND exclusive). **Not** validated with an external validator or imported into Google/Apple Calendar from this machine. | Owner: import `/calendar.ics` once after deploy. |
| Lighthouse ≥ 90 performance and accessibility | Lighthouse 12.6.1, headless Chrome, local static server, desktop and mobile presets, 7 pages: `/`, `/gsoc/`, `/gsoc/zulip/`, `/calendar/`, `/issues/`, `/gsoc/start-now/`, `/methodology/`. After two fixes (heading order on org cards; contrast of past calendar dates) **all pages score 100/100 perf and a11y on both presets**. `/issues/` scores SEO 63 because it is intentionally `noindex` until live data exists. | One desktop run of `/gsoc/` scored perf 76 (layout shift); it was not reproducible on reruns (CLS 0). Real-world Cloudflare numbers will differ; measure again after deploy. |
| Page budget ≤ 8,000 | 541 pages built (518 org + 11 year + static + RSS). Repo pages add at most 6,000 (capped in `getStaticPaths`). CI enforces the cap. | |

## Phase 2 — pipeline

| Test | Result |
|---|---|
| Unit tests | 29/29 pass (`python -m unittest discover -s pipeline/tests -t .`). |
| Offline fixture run | 4 repos / 9 issues: open 3, claimed 3, stale 2, restricted 1; second run idempotent (identical export); snapshot dump + restore round-trip equal. |
| Live GitHub Search qualifiers | Verified unauthenticated on 2026-10-21 (`docs/VERIFIED_QUALIFIERS.md`): `advanced_search=true` accepted, comma-OR labels work, `no:assignee` works, `-linked:pr` works, two `org:` qualifiers AND together (0 results) so orgs are queried one per call, `-no:assignee` is ignored. |
| Full run inside Actions limits | **Not run.** Requires `CLAIMABLE_PAT`. Budget is planned in `docs/LIMITS.md` (~4,300 GraphQL points, ~500 search calls per run); the first real run must be watched. |
| Blind 200-issue evaluation | **Not run.** Needs live data and a human labeller. Verdicts are labelled "unverified" everywhere until done. |
| Restore from a clean checkout | Tested via `run.py restore-test` on the fixture dump directory; not yet tested against a real `data` branch (none exists until first push). |

## Phase 3 — site on live data

| Test | Result |
|---|---|
| Build with live data | **Not possible yet** (no live run). Build with empty exports succeeds; every live-data page shows an explicit "pipeline has not run" notice instead of placeholder data; `/issues/` and empty repo pages are `noindex`. |
| Freshness timestamp on every issue | Issue drawer and RSS carry `fetched_at`/`generated_at`; verified in templates, not on live output. |
| RSS | `/rss/all.xml` builds; per-language and per-org feeds are generated only when there are issues for them. Not validated with the W3C feed validator (needs a public URL). |

## Phases 4–5

README, issue templates, launch drafts, methodology/data/privacy/changelog pages, weekly report workflow and keepalive check exist. None has been exercised in a real GitHub repository: the workflows have not run even once. Expect first-run breakage.
