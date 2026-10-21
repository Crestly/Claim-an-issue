"""Repository health metrics, computed from the last N closed pull requests.

Definitions (published on /methodology):
* First-time merge rate = merged / closed among PRs whose authorAssociation is
  FIRST_TIMER or FIRST_TIME_CONTRIBUTOR at fetch time, over the last 100 closed PRs.
  Shown only when closed >= 10.
* Time to first response = hours from PR creation to the first non-bot comment
  or review by an OWNER, MEMBER or COLLABORATOR. Median shown only when n >= 10.
* Bot / agent PR share (estimated) = PRs whose author is a Bot, matches a bot
  login pattern, or matches an AI-agent login pattern (copilot, claude, devin,
  cursor, codex, sweep, openhands, aider, jules, ...), divided by all PRs in the
  window. Labelled "estimated" everywhere.
* Setup friction: low = devcontainer or Dockerfile + CONTRIBUTING; medium =
  CONTRIBUTING only; high = neither; unknown = fork (community profile unavailable).
* Negative metrics are shown only after a 14-day grace period from first index.
Cost: one GraphQL query per repo, ~3-4 points (pullRequests(last:100) with
reviews(first:3) and comments(first:5)). We budget ~500 repos per run for health.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from common import now_iso, today
from enrich import AGENT_LOGIN, BOT_LOGIN
from github_api import GitHub

MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
FIRST = {"FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"}

PR_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    databaseId
    pullRequests(last: 100, states: [MERGED, CLOSED], orderBy: {field: CREATED_AT, direction: ASC}) {
      nodes {
        createdAt merged closedAt authorAssociation
        author { __typename login }
        reviews(first: 3) { nodes { createdAt authorAssociation author { __typename login } } }
        comments(first: 5) { nodes { createdAt authorAssociation author { __typename login } } }
      }
    }
  }
}
"""


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def compute(prs: list[dict]) -> dict:
    ft_closed = ft_merged = 0
    bot_n = 0
    first_resp: list[float] = []
    for pr in prs:
        author = pr.get("author") or {}
        login = author.get("login") or ""
        is_bot = author.get("__typename") == "Bot" or bool(BOT_LOGIN.search(login)) or bool(AGENT_LOGIN.search(login))
        if is_bot:
            bot_n += 1
        if (pr.get("authorAssociation") or "") in FIRST:
            ft_closed += 1
            if pr.get("merged"):
                ft_merged += 1
        created = _ts(pr.get("createdAt"))
        best = None
        for ev in ((pr.get("reviews") or {}).get("nodes", []) + (pr.get("comments") or {}).get("nodes", [])):
            a = ev.get("author") or {}
            if a.get("__typename") == "Bot" or BOT_LOGIN.search(a.get("login") or ""):
                continue
            if (ev.get("authorAssociation") or "") in MAINTAINER:
                t = _ts(ev.get("createdAt"))
                if t and created and t > created and (best is None or t < best):
                    best = t
        if best and created and not is_bot:
            first_resp.append((best - created).total_seconds() / 3600)
    n = len(prs)
    return {
        "first_time_prs_closed": ft_closed, "first_time_prs_merged": ft_merged,
        "first_time_merge_rate": (ft_merged / ft_closed) if ft_closed >= 10 else None,
        "first_response_n": len(first_resp), "median_first_response_hours": statistics.median(first_resp) if len(first_resp) >= 10 else None,
        "bot_pr_n": n, "bot_pr_count": bot_n, "bot_pr_share_estimate": (bot_n / n) if n >= 10 else None,
    }


def setup_friction(repo_row: dict) -> str:
    if repo_row.get("is_fork"):
        return "unknown"
    if (repo_row.get("has_devcontainer") or repo_row.get("has_dockerfile")) and repo_row.get("has_contributing"):
        return "low"
    if repo_row.get("has_contributing"):
        return "medium"
    return "high"


def fetch_health(gh: GitHub, repo_row: dict, log=print) -> dict | None:
    owner, name = repo_row["full_name"].split("/", 1)
    try:
        payload = gh.graphql(PR_QUERY, {"owner": owner, "name": name})
    except RuntimeError as e:
        log(f"health error {repo_row['full_name']}: {e}")
        return None
    repo = (payload.get("data") or {}).get("repository") or {}
    prs = (repo.get("pullRequests") or {}).get("nodes", [])
    m = compute(prs)
    m.update({"repo_id": repo_row["id"], "day": today(), "setup_friction": setup_friction(repo_row),
              "source": "github:graphql", "fetched_at": now_iso(), "last_verified": now_iso()})
    return m
