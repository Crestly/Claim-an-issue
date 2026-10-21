# Verified Search/GraphQL qualifiers

Generated 2026-10-21T21:08:05Z against the live GitHub API with `advanced_search=true` (authenticated).

| query | note | status | total_count | incomplete |
|---|---|---|---|---|
| `is:issue is:open label:"good first issue" archived:false` | baseline | 200 | 439145 | False |
| `is:issue is:open label:"good first issue","help wanted" archived:false` | comma between label values = OR (count should be >= baseline) | 200 | 842885 | False |
| `is:issue is:open label:"good first issue" no:assignee archived:false` | no:assignee | 200 | 319104 | False |
| `is:issue is:open label:"good first issue" -linked:pr archived:false` | -linked:pr (negated) | 200 | 401514 | False |
| `is:issue is:open label:"good first issue" comments:<6 archived:false` | comments:<6 | 200 | 411740 | False |
| `is:issue is:open label:"good first issue" updated:>2026-09-01 archived:false` | updated:>DATE | 200 | 57054 | False |
| `is:issue is:open label:"good first issue" created:2026-09-01..2026-10-01 archived:false` | created:A..B | 200 | 19432 | False |
| `is:issue is:open label:"good first issue" org:zulip archived:false` | org: qualifier | 200 | 20 | False |
| `is:issue is:open label:"good first issue" org:zulip org:sympy archived:false` | two org: qualifiers (advanced_search: AND -> expect 0) | 200 | 0 | False |
| `is:issue is:open label:"good first issue" -no:assignee archived:false` | -no:assignee (expected to be rejected or ignored) | 200 | 439145 | False |
| `is:issue is:open label:"good first issue" language:python archived:false` | language: | 200 | 75240 | False |
| `is:issue is:open label:"good first issue" no:assignee -linked:pr comments:<6 updated:>2026-09-01 created:2026-01-01..2026-10-21 archived:false` | full discovery pattern | 200 | 37822 | False |

GraphQL fields (`authorAssociation`, `assignees.totalCount`, `comments.author.__typename`, `closedByPullRequestsReferences(includeClosedPrs:true)`, `timelineItems(itemTypes:[CROSS_REFERENCED_EVENT])`): **OK**

Quota after checks: {'rest_used': 0, 'graphql_used': 1, 'search_used': 12, 'rest_remaining': None, 'graphql_remaining': 4930, 'errors': 0}
