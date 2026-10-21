# Claim an Issue

`claimanissue` · repo: [Crestly/Claim-an-issue](https://github.com/Crestly/Claim-an-issue)

A free, fast, login-free site that lists open-source issues that **genuinely need a person**, with an evidence-backed verdict for each one (open / claimed / stale claim / restricted), a published rule set and a measured error rate. On top of it: every Google Summer of Code mentoring organization 2016–2026, linked to its live newcomer issues, and one calendar for the sister programs (Outreachy, LFX Mentorship, Summer of Bitcoin, MLH Fellowship, Season of KDE).

> Status (2026-10-21): built, not launched. The pipeline has run only on offline fixtures; verdicts are labelled **unverified** until the 200-issue blind evaluation is done. Owner actions required before launch are in [`NEEDS_OWNER.md`](NEEDS_OWNER.md).

## What is different from goodfirstissue.org, up-for-grabs, firstissue.dev, etc.

Those sites are good and we link to them. They show labelled issues; we try to answer the next question: *is anyone already on it?* We fetch assignees, linked and cross-referenced PRs, and the last ten comments (read in memory, never stored), apply [published rules](site/src/pages/methodology.astro), and show the evidence next to the verdict. We also store daily snapshots so we can publish how issues and repositories behave over time. The GSoC layer and the program calendar are the second half.

Honest caveats: a copycat can build the same thing; the GitHub data is public; the measured accuracy may turn out worse than hoped. Traffic is not guaranteed.

## Layout

```
site/        Astro 5 static site (Cloudflare Pages). Single naming config: site/src/config.ts
pipeline/    Python 3.12 stdlib-only pipeline (GitHub Search + GraphQL -> SQLite -> JSON exports)
pipeline/tests/  unit tests + offline fixtures
data/curated/    hand-maintained: org aliases, org -> GitHub mapping, program dates, opt-outs
data/export/     generated JSON consumed by the site (committed by the refresh workflow)
data/raw/gsoc/   downloaded community dataset (not committed; see data/raw/gsoc/UPSTREAM-LICENSE.txt)
docs/        SCHEMA.md, LIMITS.md (every external call and its limit), OPERATIONS.md, SOURCES.md, VERIFIED_QUALIFIERS.md
eval/        blind evaluation protocol and scorer
.github/workflows/  refresh (3x/day), ci, keepalive-check, weekly-report
launch/      draft posts (owner decides whether and where to post)
```

## Run it locally

Requirements: Python 3.12+, Node 22+. No other dependencies for the pipeline.

```bash
# GSoC organisations (no token needed)
python pipeline/fetch_gsoc_dataset.py
python pipeline/build_orgs.py                # -> data/export/orgs.json, org_years.json

# Offline end-to-end check of the issue pipeline on fixtures (no network)
python pipeline/run.py fixture --out /tmp/claimable-fixture

# Unit tests
python -m unittest discover -s pipeline/tests -t .

# Live refresh (needs a fine-grained PAT with public-repo read, in CLAIMABLE_PAT)
CLAIMABLE_PAT=... python pipeline/run.py refresh --max-search-calls 50 --max-issue-batches 20 --max-health-repos 10

# Site
cd site && npm ci && npm run dev      # or npm run build -> site/dist
```

## Pipeline in one paragraph

Restore the last 45 days of snapshots from the `data` branch; load curated files; verify the GSoC org → GitHub mapping; discover newcomer-labelled issues (GSoC orgs first, then a global query sliced by creation window, `advanced_search=true`); enrich repositories (metadata, policy files, `.claimable.yml`) and issues (assignees, linked PRs, cross-references, last 10 comments with author association) via GraphQL in batches; classify each issue with `pipeline/classify.py`; compute repository health from the last 100 PRs; write JSON exports and client shards; dump the day's snapshots as gzip CSV. Limits and the per-run budget are in `docs/LIMITS.md`.

## Rules we will not break

- Never store or publish comment text, comment authors or emails. CI greps the exports for these.
- Never comment on, assign or ping issues, open PRs or message maintainers. There is no bot.
- No rankings of individuals. No ads, affiliates or mailing list at launch.
- Maintainer opt-out (issue, email, `.claimable.yml`, topic `no-claimable`) applied within 72 hours, permanently.
- Labels are untrusted signals. Verdicts carry a disclaimer and an "unverified" tag until the measured bar (claimed-vs-open precision ≥ 90 %) is met.
- "Summer of Code" is a trademark of Google; this project is not affiliated with Google or GitHub.

## Contributing

Most useful: fixing the GSoC org → GitHub mapping in `data/curated/org_github_map.csv` (format `alias,login,source,note`; source `manual:verified` if you checked the org's own site), adding claim patterns with a test in `pipeline/tests/test_classify.py`, and reporting wrong verdicts with the issue template.

## Licence

Code: MIT (`LICENSE`). Generated data: CC BY 4.0 (`data/LICENSE-DATA.md`). The GSoC organisation seed comes from [nishantwrp/gsoc-organizations](https://github.com/nishantwrp/gsoc-organizations); we republish only our own derived fields and official links.
