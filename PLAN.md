# PLAN.md — Claimable (working name)

Written 2026-10-21. This is the build plan for a free, login-free open-source
contribution finder with a GSoC organisation layer. It is written for a solo
owner on a free budget. Every external fact below is either marked with its
source or marked UNVERIFIED. Nothing here promises traffic.

## 0. Honesty frame

* Classifier accuracy is measured, not assumed. The published bar is
  claimed-vs-open precision >= 90 % on a 200-issue blind sample. Until the owner
  has produced that sample (see `eval/README.md`), the site shows verdicts as
  **"unverified"**.
* Competitors exist and can copy features. goodfirstissue.org is the strongest
  incumbent (verified 2026-10-21: skips repos with >1000 open issues AND <100
  stars, requires a commit in 180 days, indexes body text, free tier caps
  advanced filters). Our difference is not scale; it is (a) GSoC orgs linked to
  live issues across all years, (b) an open, evidenced verdict with a published
  error rate, (c) accumulated claim-lifecycle history, (d) no login, no caps,
  (e) no comment text or comment authors in our data.
* Traffic is a goal, not a promise. See section 8.

## 1. Name, domain, trademark (re-verified 2026-10-21)

| Candidate | Domain (RDAP, 2026-10-21) | Trademark findings |
|---|---|---|
| Claimable | `claimable.me` REGISTERED (resolves to Wix IPs; may already be the owner's). `.dev/.org/.app` registered. | **Conflict.** "Claimable" is a live UK registered mark (Claimable Ltd, claims software, UK00003450029 reg. 2020, further 2025 filings) and a pending US application (Claimable Inc, serial 98516533, software services). Both are software. Not recommended as the public product name. |
| **FirstPatch** (recommended) | `firstpatch.dev` likely available (RDAP 404, no DNS) | No registered mark found. Minor noise: a dead 2012 "firstpatch.me" and a 2026 hackathon project "FirstPatchAI". Owner must still run USPTO TESS, UKIPO and CIPO searches. |
| Takeable | `takeable.dev` likely available | Not searched. |
| FreeIssue / IssueFree | `.dev` likely available | Not searched. |

Rules applied: never "GSoC" / "Summer of Code" in product name, domain or
handles. GSoC may only be referenced as "[name] for GSoC Contributors" on a
page about GSoC. Footer wording is Google's exact attribution sentence
(verified at developers.google.com/open-source/gsoc/resources/brand_guidelines).

Implementation: the display name lives in one place, `site/src/config.ts`
(`SITE_NAME`, `SITE_URL`). Renaming is a one-line change plus the domain.

## 2. Re-verification of UNVERIFIED items (what changed)

| Item | Result 2026-10-21 | Action |
|---|---|---|
| GSoC 2026 timeline | Confirmed verbatim on developers.google.com/open-source/gsoc/timeline (Jan 19 org apps open; Feb 3 deadline; Feb 19 orgs announced; Mar 16–31 proposals; Apr 30 results; May 1–24 bonding; May 25 coding; Aug 17–24 final week; Nov 2 extended deadline). No 2027 dates. The page also publishes a generic month-by-month pattern. | Calendar uses 2026 as "last confirmed" and a 2027 row marked "expected pattern, not announced". |
| summerofcode.withgoogle.com robots.txt | Returns 404 (no robots file). Terms not read in a real browser. | Still not scraping. Community dataset + manual curation + link out. |
| Outreachy December 2026 round | Confirmed on outreachy.org/apply/project-selection: initial apps Aug 24–31; project list Oct 2; contribution period Oct 12 – Nov 9; interns announced Nov 30; internship Dec 7 2026 – Mar 8 2027. Open communities: Bioconductor, Debian, Git, GNOME, Linux Kernel, OCaml, OpenStack, Servo, Rust Project, Wikimedia Foundation. | Outreachy page ships with this list and official link. |
| Summer of Bitcoin 2026 dates | Homepage shows no dates. | Listed with official link, dates marked UNVERIFIED. |
| LFX Mentorship other terms | Not verified. | Listed with CNCF term 1 only; other terms marked UNVERIFIED. |
| Season of KDE | Not re-verified. | Dates kept as supplied, marked "last verified 2026-10-21 from brief, not primary". |
| goodfirstissue.org flags | /about verified. Exact names of "possibly taken" flags still UNVERIFIED (requires sign-in). | Not claimed on the site. |
| r/opensource rules | Not fetched (Reddit blocks server fetches). | Owner reads in a browser before posting. |
| "Claimable" trademark | **New finding: conflict** (see section 1). | Recommend rename to FirstPatch. |
| Community dataset licence | Code GPL-3.0 (LICENSE file saved to `data/raw/gsoc/UPSTREAM-LICENSE.txt`). Data licence not stated. Data includes `student_name`. | Issue to the maintainer drafted in `NEEDS_OWNER.md`; we publish only our own derived fields plus official links; we never publish student names or contact emails. |
| GitHub Search qualifiers | Not tested live (no token yet). | `pipeline/verify_qualifiers.py` tests each qualifier on first authenticated run and writes `docs/VERIFIED_QUALIFIERS.md`. |
| Node `node:sqlite` | Local Node is 22.2.0 (no node:sqlite). | Pipeline is Python 3.12 stdlib (`sqlite3`, `urllib`), zero third-party deps. Site is Astro (pinned). |

## 3. Architecture (as recommended, with two written changes)

```
GitHub repo (public)
├── site/           Astro 5 static site -> Cloudflare Pages  (free, unlimited static requests)
├── pipeline/       Python 3.12 stdlib only -> builds data/claimable.sqlite, exports site/public/data/*.json
├── data/
│   ├── raw/gsoc/   community dataset snapshot (not redistributed as-is)
│   ├── curated/    hand-maintained: org_github_map.csv, aliases, programs.json, optouts.json
│   └── export/     generated JSON (committed by the pipeline run)
├── eval/           blind-labelling protocol, labels CSV, scoring script
├── docs/           SCHEMA.md, METHODOLOGY.md, API.md, LIMITS.md, VERIFIED_QUALIFIERS.md
└── .github/workflows/  refresh.yml (cron), weekly-report.yml, keepalive-check.yml
```

Change 1: **pipeline in Python stdlib, not Node.** Reason: `node:sqlite` is
unavailable on the local Node 22.2; `better-sqlite3` adds a native build; Python
3.12 ships `sqlite3` and `urllib`, so there is nothing to pin or compile.

Change 2: **snapshots persisted in a `data` branch** (not Releases). Reason:
restore is a single `git fetch origin data` and works from a clean checkout;
tested by `pipeline/restore_test.sh`. Daily snapshot is a gzip of the SQLite
`issue_snapshots`/`repo_health_snapshots` tables as CSV (tens of MB a year at
launch scale). If the branch passes 1 GB we move cold months to Release assets.

Budget/limits (all documented in `docs/LIMITS.md`): Cloudflare Pages Free 500
builds/month, 20k files, 25 MiB/file; we cap generated pages at 8,000; issues
are not pages. No Workers/Functions at launch. D1 reserved for opt-outs only if
the issue/email path proves too slow (it is a JSON file in the repo at launch).

## 4. Phases

| Phase | Scope | Acceptance | Status |
|---|---|---|---|
| 0 | PLAN, NEEDS_OWNER, verification | this file | done |
| 1 | GSoC explorer 2016–2026, org pages, calendar + ICS, Start-now guide, opt-out, about | 25 random orgs spot-checked; every program entry has official link + last-verified; Lighthouse perf/a11y >= 90 | done; measured, see `docs/ACCEPTANCE.md` |
| 2 | SCHEMA.md, pipeline (discovery, enrichment, classifier, health), snapshot persistence, eval harness | blind 200-issue eval; full run within Actions limits; idempotent reruns | code done, fixture-tested; **live run and blind eval not done** (need PAT + owner) |
| 3 | Site on live data: search + filters (URL state), issue drawer with evidence, repo pages, RSS, sitemap, OG | no placeholder data on live pages; freshness timestamp everywhere | built; empty-state verified; **not seen with live data** |
| 4 | Methodology, API docs, privacy, README, issue templates, launch post drafts | drafts only; owner posts | done |
| 5 | Weekly health report, uptime, changelog | workflows exist and are tested with fixtures | workflows written; **never executed on GitHub** |

## 5. Data pipeline summary (full detail in `docs/SCHEMA.md` and `docs/METHODOLOGY.md`)

* Launch scale 3,000–5,000 repos: GSoC-org repos first (from
  `data/curated/org_github_map.csv`), then high-signal repos.
* Discovery: Search API with `advanced_search=true`, sliced by `created:` until
  `total_count < 1000`; 30 req/min; `incomplete_results` logged.
* Enrichment: GraphQL, one alias per repo, `closedByPullRequestsReferences
  (includeClosedPrs: true)`, last 10 comments (`authorAssociation`, body used
  only in memory for claim-pattern matching, never stored), timeline
  cross-references.
* Classifier states: claimed / stale_claim / open / restricted. Rules are in
  `pipeline/classify.py` and mirrored word-for-word on `/methodology`.
* Health: first-time merge rate, time to first maintainer response, setup
  friction, estimated bot/agent share, AI policy. Medians shown only with
  n >= 10; 14-day grace before negative metrics.
* Quota: one fine-grained PAT, 5,000 REST/h, 5,000 GraphQL points/h. Planned
  10–15k repo-page refreshes/day. Hot repos 2–3x/day, cold weekly.

## 6. Legal and policy (hard)

* No comment text, no comment authors, no emails in API or dump.
* Opt-out: GitHub issue template or email; applied within 72 h; permanent;
  also `.claimable.yml` with `index: false` or topic `no-claimable`.
* Never comment, assign, ping or open PRs anywhere. No bots.
* Footer: `"Summer of Code" is a trademark of Google and {SITE_NAME} is not affiliated with Google or Google's Summer of Code.`
* Every verdict labelled "automated estimate; GitHub is the source of truth".
* No ads, no affiliate links, no email list at launch.

## 7. Growth plan (goal, not promise)

Days 1–7 GSoC explorer + calendar + opt-out + RSS live; sitemap to Search
Console. Days 8–14 DEV `#showdev` post (draft in `launch/`). Days 15–21 Show HN
(draft in `launch/`), awesome-list PRs, daily.dev source application. Days
22–30 Search Console review; prepare for Jan 19 – Feb 3 2027 org window.
Re-review after Feb 3 2027.

## 8. Day-30 review criteria

Classifier precision >= 90 % on a fresh sample; pipeline ran >= 27 of 30 days;
verdict error reports per 1,000 drawer opens. If usage is near zero after the
Feb 2027 review, write a post-mortem and propose the smallest change (likely:
keep only the GSoC layer).

## 9. Open risks

1. Trademark on "Claimable" (section 1). Mitigation: rename before launch.
2. The 200-issue blind evaluation requires the owner's time (about 3–4 hours).
   Verdicts are "unverified" until done.
3. GitHub Search qualifiers untested until a token exists.
4. Scheduled workflows disable after 60 days of inactivity; `keepalive-check`
   re-enables via the Actions API with the owner's PAT and opens an issue if a
   run is missed. Whether bot commits reset the timer is unproven; we do not
   rely on it.
5. The community dataset's data licence is unstated. We do not redistribute its
   descriptions; we ask first.
