"""Verify Search API qualifiers and GraphQL field names against the live API.
Runs automatically on the first authenticated refresh (and on demand) and
writes docs/VERIFIED_QUALIFIERS.md. Costs ~12 search requests and 1 GraphQL point.

    CLAIMABLE_PAT=... python pipeline/verify_qualifiers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DOCS, env, now_iso  # noqa: E402
from github_api import GitHub  # noqa: E402

CHECKS = [
    ("is:issue is:open label:\"good first issue\" archived:false", "baseline"),
    ("is:issue is:open label:\"good first issue\",\"help wanted\" archived:false", "comma between label values = OR (count should be >= baseline)"),
    ("is:issue is:open label:\"good first issue\" no:assignee archived:false", "no:assignee"),
    ("is:issue is:open label:\"good first issue\" -linked:pr archived:false", "-linked:pr (negated)"),
    ("is:issue is:open label:\"good first issue\" comments:<6 archived:false", "comments:<6"),
    ("is:issue is:open label:\"good first issue\" updated:>2026-09-01 archived:false", "updated:>DATE"),
    ("is:issue is:open label:\"good first issue\" created:2026-09-01..2026-10-01 archived:false", "created:A..B"),
    ("is:issue is:open label:\"good first issue\" org:zulip archived:false", "org: qualifier"),
    ("is:issue is:open label:\"good first issue\" org:zulip org:sympy archived:false", "two org: qualifiers (advanced_search: AND -> expect 0)"),
    ("is:issue is:open label:\"good first issue\" -no:assignee archived:false", "-no:assignee (expected to be rejected or ignored)"),
    ("is:issue is:open label:\"good first issue\" language:python archived:false", "language:"),
    ("is:issue is:open label:\"good first issue\" no:assignee -linked:pr comments:<6 updated:>2026-09-01 created:2026-01-01..2026-10-21 archived:false", "full discovery pattern"),
]

GQL = """
query { repository(owner: "zulip", name: "zulip") { issues(first: 1, states: OPEN, labels: ["good first issue"]) { nodes {
  number authorAssociation
  assignees(first: 1) { totalCount }
  comments(last: 1) { totalCount nodes { authorAssociation author { __typename } } }
  closedByPullRequestsReferences(first: 1, includeClosedPrs: true) { totalCount nodes { state } }
  timelineItems(last: 1, itemTypes: [CROSS_REFERENCED_EVENT]) { totalCount }
} } } }
"""


def main() -> int:
    token = env("CLAIMABLE_PAT") or env("GITHUB_TOKEN")
    if not token:
        print("CLAIMABLE_PAT not set; running Search checks unauthenticated (10 req/min); GraphQL check skipped.")
    gh = GitHub(token)
    lines = [f"# Verified Search/GraphQL qualifiers\n\nGenerated {now_iso()} against the live GitHub API with `advanced_search=true` "
             f"({'authenticated' if token else 'UNAUTHENTICATED: Search checks only'}).\n",
             "| query | note | status | total_count | incomplete |", "|---|---|---|---|---|"]
    for q, note in CHECKS:
        status, body = gh.search_issues(q, per_page=1)
        total = body.get("total_count") if isinstance(body, dict) else (body.get("message") if isinstance(body, dict) else "")
        inc = body.get("incomplete_results") if isinstance(body, dict) else ""
        lines.append(f"| `{q}` | {note} | {status} | {total} | {inc} |")
        print(status, total, "|", q)
    try:
        if not token:
            raise RuntimeError("skipped (no token)")
        payload = gh.graphql(GQL)
        ok = "errors" not in payload
        lines.append(f"\nGraphQL fields (`authorAssociation`, `assignees.totalCount`, `comments.author.__typename`, `closedByPullRequestsReferences(includeClosedPrs:true)`, `timelineItems(itemTypes:[CROSS_REFERENCED_EVENT])`): **{'OK' if ok else 'ERRORS'}**")
        if not ok:
            lines.append("```\n" + str(payload.get("errors"))[:1500] + "\n```")
        print("graphql", "OK" if ok else payload.get("errors"))
    except Exception as e:  # noqa: BLE001
        lines.append(f"\nGraphQL check failed: {e}")
        print("graphql failed", e)
    lines.append(f"\nQuota after checks: {gh.budget.summary()}\n")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "VERIFIED_QUALIFIERS.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote docs/VERIFIED_QUALIFIERS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
