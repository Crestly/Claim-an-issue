"""GraphQL enrichment: repositories (metadata, policy files) and issues
(assignees, linked PRs, cross-references, last comments).

Costs (GraphQL points = nodes requested / 100, min 1 per connection):
* repo batch of 25: ~1-2 points.
* issue batch of 50 with comments(last:10), closedByPullRequestsReferences(first:10),
  timelineItems(last:25), labels(first:20), assignees(first:5): ~4 points.
Field names: Issue.closedByPullRequestsReferences(first, includeClosedPrs,
orderBy) -> PullRequestConnection (includeClosedPrs defaults to false);
Issue.timelineItems(itemTypes:[CROSS_REFERENCED_EVENT]); IssueComment.authorAssociation.
verify_qualifiers.py checks these against the live schema on first authenticated run.

Comment bodies are fetched for in-memory claim-pattern matching and discarded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from common import now_iso
from github_api import GitHub
from policy import POLICY_FILES, detect_ai_policy, detect_first_time_restriction, parse_claimable_yml

BOT_LOGIN = re.compile(r"\[bot\]$|^(dependabot|renovate|github-actions|codecov|copilot|coderabbitai|sonarcloud|stale|mergify|allcontributors|netlify|vercel)\b", re.I)
AGENT_LOGIN = re.compile(r"copilot|claude|devin|cursor|codex|sweep|openhands|aider|jules|gemini|amazon-q|qodo|blackbox|gpt-engineer", re.I)


def _alias(i: int) -> str:
    return f"n{i}"


def _ident(owner: str, name: str) -> str:
    return f'owner: {json.dumps(owner)}, name: {json.dumps(name)}'


# ------------------------------------------------------------------ repositories
REPO_FIELDS = """
  databaseId id nameWithOwner name owner { login __typename } description primaryLanguage { name }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  stargazerCount forkCount isFork isArchived isDisabled pushedAt
  defaultBranchRef { name }
  issuesOpen: issues(states: OPEN) { totalCount }
  f_contrib: object(expression: "HEAD:CONTRIBUTING.md") { ... on Blob { text byteSize } }
  f_contrib2: object(expression: "HEAD:.github/CONTRIBUTING.md") { ... on Blob { text byteSize } }
  f_contrib3: object(expression: "HEAD:docs/CONTRIBUTING.md") { ... on Blob { text byteSize } }
  f_ai: object(expression: "HEAD:AI_POLICY.md") { ... on Blob { text byteSize } }
  f_agents: object(expression: "HEAD:AGENTS.md") { ... on Blob { text byteSize } }
  f_claimable: object(expression: "HEAD:.claimable.yml") { ... on Blob { text } }
  f_devcontainer: object(expression: "HEAD:.devcontainer") { __typename }
  f_devcontainer2: object(expression: "HEAD:.devcontainer.json") { __typename }
  f_docker: object(expression: "HEAD:Dockerfile") { __typename }
  f_compose: object(expression: "HEAD:docker-compose.yml") { __typename }
  f_coc: object(expression: "HEAD:CODE_OF_CONDUCT.md") { __typename }
  f_issue_tpl: object(expression: "HEAD:.github/ISSUE_TEMPLATE") { __typename }
  f_pr_tpl: object(expression: "HEAD:.github/PULL_REQUEST_TEMPLATE.md") { __typename }
"""


def build_repo_query(full_names: list[str]) -> str:
    parts = []
    for i, fn in enumerate(full_names):
        owner, name = fn.split("/", 1)
        parts.append(f"{_alias(i)}: repository({_ident(owner, name)}) {{ {REPO_FIELDS} }}")
    return "query { " + " ".join(parts) + " }"


def _blob_text(node, limit: int = 60000) -> str | None:
    if not node or "text" not in node:
        return None
    t = node.get("text") or ""
    return t[:limit]


def normalise_repo(node: dict, *, opted_out_targets: set[str], org_slug: str | None) -> dict:
    files = {
        "CONTRIBUTING.md": _blob_text(node.get("f_contrib")),
        ".github/CONTRIBUTING.md": _blob_text(node.get("f_contrib2")),
        "docs/CONTRIBUTING.md": _blob_text(node.get("f_contrib3")),
        "AI_POLICY.md": _blob_text(node.get("f_ai")),
        "AGENTS.md": _blob_text(node.get("f_agents")),
    }
    yml = parse_claimable_yml(_blob_text(node.get("f_claimable")))
    topics = [t["topic"]["name"] for t in (node.get("repositoryTopics") or {}).get("nodes", []) if t.get("topic")]
    policy, policy_src = detect_ai_policy(files, override=yml.get("ai_policy"))
    restricted, _ = detect_first_time_restriction(files)
    if yml.get("claim_required") is True:
        pass  # informational; shown on repo page, not a restriction
    full = node["nameWithOwner"]
    owner = node["owner"]["login"]
    opted = (owner.lower() in opted_out_targets) or (full.lower() in opted_out_targets) or (yml.get("index") is False) or ("no-claimable" in topics)
    return {
        "id": node["databaseId"], "node_id": node["id"], "full_name": full, "owner": owner, "name": node["name"],
        "description": (node.get("description") or "")[:300] or None,
        "language": (node.get("primaryLanguage") or {}).get("name"), "topics_json": json.dumps(topics),
        "stars": node.get("stargazerCount", 0), "forks": node.get("forkCount", 0), "open_issues": (node.get("issuesOpen") or {}).get("totalCount", 0),
        "is_fork": int(bool(node.get("isFork"))), "archived": int(bool(node.get("isArchived"))), "disabled": int(bool(node.get("isDisabled"))),
        "pushed_at": node.get("pushedAt"), "default_branch": (node.get("defaultBranchRef") or {}).get("name"),
        "gsoc_org_slug": org_slug, "opted_out": int(opted), "claimable_yml_json": json.dumps(yml) if yml else None,
        "ai_policy": policy, "ai_policy_source": policy_src, "restricted_first_time_prs": int(restricted),
        "has_contributing": int(any(files[k] for k in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"))),
        "has_code_of_conduct": int(bool(node.get("f_coc"))), "has_issue_template": int(bool(node.get("f_issue_tpl"))), "has_pr_template": int(bool(node.get("f_pr_tpl"))),
        "has_devcontainer": int(bool(node.get("f_devcontainer") or node.get("f_devcontainer2"))), "has_dockerfile": int(bool(node.get("f_docker") or node.get("f_compose"))),
        "source": "github:graphql", "fetched_at": now_iso(), "last_verified": now_iso(),
    }


# ------------------------------------------------------------------------ issues
ISSUE_FIELDS = """
  databaseId id number title url state createdAt updatedAt closedAt authorAssociation
  author { __typename }
  labels(first: 20) { nodes { name } }
  assignees(first: 5) { totalCount }
  comments(last: 10) { totalCount nodes { databaseId url createdAt authorAssociation author { __typename login } body } }
  closedByPullRequestsReferences(first: 10, includeClosedPrs: true) { nodes { url state createdAt } }
  timelineItems(last: 25, itemTypes: [CROSS_REFERENCED_EVENT]) {
    nodes { ... on CrossReferencedEvent { createdAt source { __typename ... on PullRequest { url state createdAt } } } }
  }
"""


def build_issue_query(refs: list[tuple[str, int]]) -> str:
    """refs: [(owner/name, number)]. One alias per issue."""
    parts = []
    for i, (fn, number) in enumerate(refs):
        owner, name = fn.split("/", 1)
        parts.append(f"{_alias(i)}: repository({_ident(owner, name)}) {{ issue(number: {int(number)}) {{ {ISSUE_FIELDS} }} }}")
    return "query { " + " ".join(parts) + " }"


def normalise_graphql_issue(node: dict, repo_row: dict) -> dict:
    """Shape consumed by classify.classify(). Comment bodies stay in memory only."""
    comments = []
    for c in (node.get("comments") or {}).get("nodes", []):
        author = c.get("author") or {}
        login = author.get("login") or ""
        is_bot = author.get("__typename") == "Bot" or bool(BOT_LOGIN.search(login))
        comments.append({
            "author_key": login,  # transient; never persisted
            "author_association": c.get("authorAssociation"), "is_bot": is_bot, "created_at": c.get("createdAt"),
            "body": c.get("body") or "", "url": c.get("url"),
        })
    linked = [{"state": p.get("state"), "url": p.get("url"), "created_at": p.get("createdAt")} for p in (node.get("closedByPullRequestsReferences") or {}).get("nodes", [])]
    xrefs = []
    for ev in (node.get("timelineItems") or {}).get("nodes", []):
        src = (ev or {}).get("source") or {}
        if src.get("__typename") == "PullRequest":
            xrefs.append({"state": src.get("state"), "url": src.get("url"), "created_at": src.get("createdAt") or ev.get("createdAt")})
    yml = json.loads(repo_row.get("claimable_yml_json") or "{}")
    return {
        "id": node["databaseId"], "node_id": node["id"], "number": node["number"], "title": node.get("title", ""), "url": node.get("url"),
        "state_gh": (node.get("state") or "OPEN").lower(), "labels": [l["name"] for l in (node.get("labels") or {}).get("nodes", [])],
        "created_at": node.get("createdAt"), "updated_at": node.get("updatedAt"), "closed_at": node.get("closedAt"),
        "comments_count": (node.get("comments") or {}).get("totalCount", 0),
        "has_assignee": (node.get("assignees") or {}).get("totalCount", 0) > 0, "assignee_count": (node.get("assignees") or {}).get("totalCount", 0),
        "linked_prs": linked, "crossref_prs": xrefs, "comments": comments,
        "author_is_first_timer": int((node.get("authorAssociation") or "") in ("FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR")),
        "repo": {
            "ai_policy": repo_row.get("ai_policy", "unknown"), "restricted_first_time_prs": bool(repo_row.get("restricted_first_time_prs")),
            "claim_commands": yml.get("claim_commands") or [], "newcomer_labels": yml.get("labels") or [],
        },
    }


def fetch_repos(gh: GitHub, full_names: list[str], *, opted_out_targets: set[str], org_of: dict[str, str | None], batch: int = 25, log=print) -> list[dict]:
    out = []
    for i in range(0, len(full_names), batch):
        chunk = full_names[i:i + batch]
        try:
            payload = gh.graphql(build_repo_query(chunk))
        except RuntimeError as e:
            log(f"repo batch error: {e}")
            continue
        data = payload.get("data") or {}
        for j, fn in enumerate(chunk):
            node = data.get(_alias(j))
            if node:
                out.append(normalise_repo(node, opted_out_targets=opted_out_targets, org_slug=org_of.get(fn.lower())))
    return out


def fetch_issues(gh: GitHub, refs: list[tuple[str, int]], repo_rows: dict[str, dict], batch: int = 50, log=print):
    for i in range(0, len(refs), batch):
        chunk = refs[i:i + batch]
        try:
            payload = gh.graphql(build_issue_query(chunk))
        except RuntimeError as e:
            log(f"issue batch error: {e}")
            continue
        data = payload.get("data") or {}
        for j, (fn, _) in enumerate(chunk):
            node = (data.get(_alias(j)) or {}).get("issue")
            if node and fn.lower() in repo_rows:
                yield fn, normalise_graphql_issue(node, repo_rows[fn.lower()])
