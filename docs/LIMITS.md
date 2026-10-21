# LIMITS.md â€” every external call and its limit

| Call | Where | Limit (verified source) | How we stay inside |
|---|---|---|---|
| `GET /search/issues?advanced_search=true` | `discover.py` | 30 req/min authenticated, 10/min anonymous; 1,000 results/query; counts against the separate `search` bucket | Client throttles to 28/min (9 anonymous); windows sliced by `created:` until `total_count < 1000`; `--max-search-calls` (default 500/run) |
| `POST /graphql` | `enrich.py`, `health.py`, `run.verify_mapping` | 5,000 points/h per token; 2,000 points/min secondary; cost = Î£ max(1, first/100) per connection Ã· 100 | `rateLimit{cost remaining}` read on every query; stop at 400 points remaining; issue batches of 50 (~4 points), repo batches of 25 (~2 points), health 1 query/repo (~3â€“4 points), `--max-issue-batches` 600 (~2,400 points), `--max-health-repos` 400 (~1,500 points) |
| `GET /rate_limit` | run start | free | once per run |
| `GET /repos/{o}/{r}/contents/{path}` | `github_api.get_file` (fallback only) | REST core 5,000/h | not used in the default path (policy files come via GraphQL `object(expression:)`) |
| `GET /repos/{o}/{r}/community/profile` | planned | REST core; not available for forks | replaced by GraphQL file-presence checks (CONTRIBUTING, CODE_OF_CONDUCT, templates); forks get `setup_friction = unknown` |
| `PUT /repos/{o}/{r}/actions/workflows/{id}/enable` | `keepalive-check.yml` | REST core | weekly, 2 calls |
| `GET /repos/{o}/{r}/actions/workflows/{id}/runs` | `keepalive-check.yml` | REST core | weekly, 1 call |
| raw.githubusercontent.com (community GSoC dataset, 11 files) | `fetch_gsoc_dataset.py` | none practical | once per build |
| Secondary limits (403/429) | all | 100 concurrent; 900 REST points/min; `Retry-After` | sequential client; sleeps `Retry-After`+1 s or exponential 60/120/240 s |

Per-run plan on one token (3 runs/day):

| step | typical cost |
|---|---|
| org discovery (~270 logins) | ~300 search calls (~11 min at 28/min) |
| global discovery | ~100â€“200 search calls |
| repo metadata (â‰¤ 5,000 repos / 25) | â‰¤ 200 queries, ~400 points |
| issue enrichment (â‰¤ 30,000 / 50) | â‰¤ 600 queries, ~2,400 points |
| health (â‰¤ 400 repos) | ~1,500 points |
| **total** | ~4,300 GraphQL points of 5,000; ~500 search calls |

Wall time is dominated by search throttling (~20 min) and sequential GraphQL
(~1,000 requests Ã— ~1 s â‰ˆ 17 min): well under the 6 h job cap. Cron drift is
expected; the keepalive check tolerates a 36 h gap before alerting.

Hosting: Cloudflare Pages Free â€” 500 builds/month (we trigger â‰¤ 3/day from the
data commits â‰ˆ 90/month), 20,000 files, 25 MiB/file. We cap at 8,000 HTML pages
(CI asserts) and â‰¤ 19,000 files. No Workers/Functions at launch (Workers Free:
100k requests/day, 10 ms CPU). D1 (5M reads/day, 100k writes/day, 5 GB) is
reserved and unused.
