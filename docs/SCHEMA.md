# SCHEMA.md — SQLite schema for the pipeline

Database: `data/claimable.sqlite` (rebuilt each run; history persisted to the
`data` branch, see `docs/OPERATIONS.md`). Every table carries `source`,
`fetched_at` and `last_verified` (ISO-8601 UTC). Booleans are 0/1. No table
stores comment text, comment authors or email addresses.

## orgs
GSoC mentoring organisations (one row per merged organisation).

| column | type | notes |
|---|---|---|
| slug | TEXT PK | URL slug, stable |
| name | TEXT | canonical display name (latest participation) |
| category | TEXT | |
| url, ideas_url, guide_url, chat_url, mailing_list | TEXT | official links, latest non-empty |
| topics_json, technologies_json | TEXT | JSON arrays, last three participations |
| first_year, last_year, years_count, total_projects | INTEGER | |
| source, fetched_at, last_verified | TEXT | |

## org_years
| org_slug FK, year INTEGER, num_projects INTEGER, projects_url TEXT, source, fetched_at, last_verified | PK (org_slug, year) |

## org_aliases
| alias TEXT PK, org_slug FK, source, fetched_at, last_verified |

## org_github_map
| org_slug FK, github_login TEXT, kind TEXT ('org'/'user'), mapping_source TEXT ('manual'/'derived:homepage'/...), verified INTEGER, source, fetched_at, last_verified | PK (org_slug, github_login) |

## repos
| column | type | notes |
|---|---|---|
| id | INTEGER PK | GitHub database id |
| node_id | TEXT | GraphQL id |
| full_name | TEXT UNIQUE | owner/name |
| owner, name | TEXT | |
| description | TEXT | repo description (public, repo-level, not a comment) |
| language | TEXT | primary language |
| topics_json | TEXT | |
| stars, forks, open_issues | INTEGER | |
| is_fork, archived, disabled | INTEGER | |
| pushed_at | TEXT | |
| default_branch | TEXT | |
| gsoc_org_slug | TEXT FK nullable | |
| tier | TEXT | 'hot' / 'warm' / 'cold' refresh tier |
| opted_out | INTEGER | from optouts or `.claimable.yml` / topic |
| claimable_yml_json | TEXT nullable | parsed `.claimable.yml` (subset) |
| ai_policy | TEXT | allows / disclosure / forbids / forbids-gfi / unknown |
| ai_policy_source | TEXT nullable | file path + matched rule id |
| restricted_first_time_prs | INTEGER | |
| has_contributing, has_code_of_conduct, has_issue_template, has_pr_template | INTEGER | from community profile (not for forks) |
| has_devcontainer, has_dockerfile | INTEGER | |
| last_maintainer_activity | TEXT nullable | last commit/comment/review by OWNER/MEMBER/COLLABORATOR seen |
| source, fetched_at, last_verified | TEXT | |

## repo_health_snapshots
One row per repo per day the health job ran.

| repo_id FK, day TEXT (YYYY-MM-DD), first_time_prs_closed INTEGER, first_time_prs_merged INTEGER, first_time_merge_rate REAL nullable, first_response_n INTEGER, median_first_response_hours REAL nullable, bot_pr_n INTEGER, bot_pr_count INTEGER, bot_pr_share_estimate REAL nullable, setup_friction TEXT, open_claimable INTEGER, source, fetched_at, last_verified | PK (repo_id, day) |

## issues
Current state of each tracked issue.

| column | type | notes |
|---|---|---|
| id | INTEGER PK | GitHub database id |
| node_id | TEXT | |
| repo_id | INTEGER FK | |
| number | INTEGER | |
| title | TEXT | |
| url | TEXT | html_url |
| state_gh | TEXT | open / closed (we keep closed for outcome stats) |
| labels_json | TEXT | |
| created_at, updated_at, closed_at | TEXT | |
| comments_count | INTEGER | |
| has_assignee | INTEGER | count > 0; logins not stored |
| assignee_count | INTEGER | |
| linked_pr_open, linked_pr_closed, linked_pr_merged | INTEGER | counts from closedByPullRequestsReferences |
| crossref_pr_open | INTEGER | open PRs cross-referencing this issue |
| claim_comment_at | TEXT nullable | timestamp of most recent matched claim comment |
| claim_pattern_id | TEXT nullable | which rule matched (never the text) |
| claim_by_maintainer | INTEGER | the claim comment author association was OWNER/MEMBER/COLLABORATOR |
| maintainer_rebuttal_at | TEXT nullable | maintainer comment after the claim comment |
| last_activity_at | TEXT | max(updated_at, last comment, last timeline event) |
| claim_state | TEXT | open / claimed / stale_claim / restricted |
| evidence_json | TEXT | array of {kind, detail, url, at}; derived text only |
| first_maintainer_response_at | TEXT nullable | first non-bot OWNER/MEMBER/COLLABORATOR comment |
| author_is_first_timer | INTEGER | issue author association FIRST_TIMER / FIRST_TIME_CONTRIBUTOR |
| source, fetched_at, last_verified | TEXT | |

## issue_snapshots
Daily state for outcome measurement.

| issue_id FK, day TEXT, claim_state TEXT, state_gh TEXT, has_assignee INTEGER, linked_pr_open INTEGER, linked_pr_merged INTEGER, comments_count INTEGER, source, fetched_at, last_verified | PK (issue_id, day) |

## claim_events
Transitions derived by diffing consecutive snapshots (and enrichment within a run).

| id INTEGER PK, issue_id FK, at TEXT, event TEXT ('claimed','unclaimed','pr_opened','pr_merged','pr_closed','stale','closed','reopened'), from_state TEXT, to_state TEXT, source, fetched_at, last_verified |

## programs
| id TEXT PK, name, short, official_url, timeline_url, eligibility_url, audience, status, source, fetched_at, last_verified |

## program_dates
| program_id FK, start TEXT, end TEXT nullable, title TEXT, kind TEXT, status TEXT, source, fetched_at, last_verified | PK (program_id, start, title) |

## optouts
| target TEXT PK ('owner' or 'owner/repo'), method TEXT ('issue','email','claimable.yml','topic'), requested_at TEXT, applied_at TEXT, note TEXT, source, fetched_at, last_verified |

## eval_labels
| sample_date TEXT, issue_url TEXT, human_label TEXT (open/claimed/stale_claim/restricted/unsure), labeller TEXT, labelled_at TEXT, classifier_label TEXT nullable (filled only at scoring time), source, fetched_at, last_verified | PK (sample_date, issue_url) |

## runs
| run_id TEXT PK, started_at, finished_at, rest_used, graphql_used, search_used, repos_refreshed, issues_seen, errors INTEGER, notes TEXT |

## Indexes
`issues(repo_id)`, `issues(claim_state)`, `issues(updated_at)`, `issue_snapshots(day)`, `repo_health_snapshots(day)`, `repos(gsoc_org_slug)`, `repos(tier)`.

## Export mapping
`data/export/issues.json` <- `issues` where `state_gh='open'` and repo not opted out, joined with repo language and org slug; `repos.json` <- `repos` + latest `repo_health_snapshots`; `meta.json` <- `runs` + eval summary; `api/v1/*.json` are the same shapes with a `version` wrapper. Client shards: `site/public/data/issues/{language}.json` and `site/public/data/issues/index.json`.
