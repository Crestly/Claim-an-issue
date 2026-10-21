"""SQLite schema (see docs/SCHEMA.md) and small helpers. Stdlib only."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from common import DB_PATH

META = "source TEXT NOT NULL DEFAULT '', fetched_at TEXT NOT NULL DEFAULT '', last_verified TEXT"

SCHEMA = f"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS orgs (
  slug TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, url TEXT, ideas_url TEXT, guide_url TEXT,
  chat_url TEXT, mailing_list TEXT, topics_json TEXT, technologies_json TEXT,
  first_year INTEGER, last_year INTEGER, years_count INTEGER, total_projects INTEGER, {META});
CREATE TABLE IF NOT EXISTS org_years (
  org_slug TEXT NOT NULL REFERENCES orgs(slug), year INTEGER NOT NULL, num_projects INTEGER, projects_url TEXT, {META},
  PRIMARY KEY (org_slug, year));
CREATE TABLE IF NOT EXISTS org_aliases (alias TEXT PRIMARY KEY, org_slug TEXT NOT NULL REFERENCES orgs(slug), {META});
CREATE TABLE IF NOT EXISTS org_github_map (
  org_slug TEXT NOT NULL REFERENCES orgs(slug), github_login TEXT NOT NULL, kind TEXT, mapping_source TEXT,
  verified INTEGER NOT NULL DEFAULT 0, {META}, PRIMARY KEY (org_slug, github_login));

CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY, node_id TEXT, full_name TEXT UNIQUE NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
  description TEXT, language TEXT, topics_json TEXT, stars INTEGER, forks INTEGER, open_issues INTEGER,
  is_fork INTEGER DEFAULT 0, archived INTEGER DEFAULT 0, disabled INTEGER DEFAULT 0, pushed_at TEXT, default_branch TEXT,
  gsoc_org_slug TEXT, tier TEXT DEFAULT 'warm', opted_out INTEGER DEFAULT 0, claimable_yml_json TEXT,
  ai_policy TEXT DEFAULT 'unknown', ai_policy_source TEXT, restricted_first_time_prs INTEGER DEFAULT 0,
  has_contributing INTEGER, has_code_of_conduct INTEGER, has_issue_template INTEGER, has_pr_template INTEGER,
  has_devcontainer INTEGER, has_dockerfile INTEGER, last_maintainer_activity TEXT, {META});
CREATE INDEX IF NOT EXISTS idx_repos_org ON repos(gsoc_org_slug);
CREATE INDEX IF NOT EXISTS idx_repos_tier ON repos(tier);

CREATE TABLE IF NOT EXISTS repo_health_snapshots (
  repo_id INTEGER NOT NULL REFERENCES repos(id), day TEXT NOT NULL,
  first_time_prs_closed INTEGER, first_time_prs_merged INTEGER, first_time_merge_rate REAL,
  first_response_n INTEGER, median_first_response_hours REAL,
  bot_pr_n INTEGER, bot_pr_count INTEGER, bot_pr_share_estimate REAL,
  setup_friction TEXT, open_claimable INTEGER, {META}, PRIMARY KEY (repo_id, day));
CREATE INDEX IF NOT EXISTS idx_rhs_day ON repo_health_snapshots(day);

CREATE TABLE IF NOT EXISTS issues (
  id INTEGER PRIMARY KEY, node_id TEXT, repo_id INTEGER NOT NULL REFERENCES repos(id), number INTEGER NOT NULL,
  title TEXT, url TEXT, state_gh TEXT, labels_json TEXT, created_at TEXT, updated_at TEXT, closed_at TEXT,
  comments_count INTEGER, has_assignee INTEGER DEFAULT 0, assignee_count INTEGER DEFAULT 0,
  linked_pr_open INTEGER DEFAULT 0, linked_pr_closed INTEGER DEFAULT 0, linked_pr_merged INTEGER DEFAULT 0,
  crossref_pr_open INTEGER DEFAULT 0, claim_comment_at TEXT, claim_pattern_id TEXT, claim_by_maintainer INTEGER DEFAULT 0,
  maintainer_rebuttal_at TEXT, last_activity_at TEXT, claim_state TEXT, evidence_json TEXT,
  first_maintainer_response_at TEXT, author_is_first_timer INTEGER DEFAULT 0, {META});
CREATE INDEX IF NOT EXISTS idx_issues_repo ON issues(repo_id);
CREATE INDEX IF NOT EXISTS idx_issues_state ON issues(claim_state);
CREATE INDEX IF NOT EXISTS idx_issues_updated ON issues(updated_at);

CREATE TABLE IF NOT EXISTS issue_snapshots (
  issue_id INTEGER NOT NULL, day TEXT NOT NULL, claim_state TEXT, state_gh TEXT, has_assignee INTEGER,
  linked_pr_open INTEGER, linked_pr_merged INTEGER, comments_count INTEGER, {META}, PRIMARY KEY (issue_id, day));
CREATE INDEX IF NOT EXISTS idx_is_day ON issue_snapshots(day);

CREATE TABLE IF NOT EXISTS claim_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL, at TEXT NOT NULL, event TEXT NOT NULL,
  from_state TEXT, to_state TEXT, {META});
CREATE UNIQUE INDEX IF NOT EXISTS idx_ce_unique ON claim_events(issue_id, at, event);

CREATE TABLE IF NOT EXISTS programs (
  id TEXT PRIMARY KEY, name TEXT, short TEXT, official_url TEXT, timeline_url TEXT, eligibility_url TEXT,
  audience TEXT, status TEXT, {META});
CREATE TABLE IF NOT EXISTS program_dates (
  program_id TEXT NOT NULL REFERENCES programs(id), start TEXT NOT NULL, end TEXT, title TEXT NOT NULL, kind TEXT,
  status TEXT, {META}, PRIMARY KEY (program_id, start, title));

CREATE TABLE IF NOT EXISTS optouts (
  target TEXT PRIMARY KEY, method TEXT, requested_at TEXT, applied_at TEXT, note TEXT, {META});

CREATE TABLE IF NOT EXISTS eval_labels (
  sample_date TEXT NOT NULL, issue_url TEXT NOT NULL, human_label TEXT, labeller TEXT, labelled_at TEXT,
  classifier_label TEXT, {META}, PRIMARY KEY (sample_date, issue_url));

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, rest_used INTEGER DEFAULT 0, graphql_used INTEGER DEFAULT 0,
  search_used INTEGER DEFAULT 0, repos_refreshed INTEGER DEFAULT 0, issues_seen INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0, notes TEXT);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, table: str, row: dict, keys: list[str]) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT({','.join(keys)}) DO UPDATE SET {updates}"
    conn.execute(sql, [row[c] for c in cols])
