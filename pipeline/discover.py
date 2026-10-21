"""Issue discovery through the GitHub Search API.

Pattern (advanced_search=true; verify qualifiers with verify_qualifiers.py):
  is:issue is:open archived:false [no:assignee -linked:pr] label:"good first issue","help wanted",...
  comments:<6 updated:>DATE created:A..B
A comma between label values means OR. `no:` cannot be negated. Results are
capped at 1,000 per query, so we slice by `created:` window (and language when
needed) until total_count < 1000. `incomplete_results` is logged.

Two discovery modes:
* org mode  (GSoC orgs):  org:LOGIN + labels, including assigned/linked issues,
  so organisation pages can show claimed states and we observe lifecycles.
* global mode: labels + no:assignee -linked:pr + updated:>30d, sliced by created
  window; produces the candidate pool for the general index.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from github_api import GitHub, RateLimited

LABELS = ["good first issue", "help wanted", "up-for-grabs", "first-timers-only", "beginner", "easy", "low-hanging-fruit", "difficulty: easy", "good-first-issue", "E-easy"]
LANGUAGES = ["python", "javascript", "typescript", "java", "go", "rust", "c", "c++", "c#", "php", "ruby", "kotlin", "swift", "dart", "scala", "shell", "html", "css"]


def label_clause(labels: list[str] | None = None) -> str:
    return "label:" + ",".join(f'"{l}"' if " " in l or ":" in l else l for l in (labels or LABELS))


def base_query(*, unassigned_only: bool, updated_within_days: int | None = 30, max_comments: int | None = 6) -> str:
    parts = ["is:issue", "is:open", "archived:false", label_clause()]
    if unassigned_only:
        parts += ["no:assignee", "-linked:pr"]
    if max_comments is not None:
        parts.append(f"comments:<{max_comments}")
    if updated_within_days:
        d = (datetime.now(timezone.utc) - timedelta(days=updated_within_days)).date().isoformat()
        parts.append(f"updated:>{d}")
    return " ".join(parts)


def _item(it: dict) -> dict:
    """Reduce a search result to the fields we keep (no body, no user details)."""
    repo_url = it.get("repository_url", "")
    full_name = "/".join(repo_url.rsplit("/", 2)[-2:]) if repo_url else ""
    return {
        "id": it["id"], "node_id": it.get("node_id"), "number": it["number"], "title": it.get("title", ""), "url": it.get("html_url"),
        "repo_full_name": full_name, "labels": [l["name"] for l in it.get("labels", [])], "created_at": it.get("created_at"),
        "updated_at": it.get("updated_at"), "comments": it.get("comments", 0), "has_assignee": bool(it.get("assignee") or it.get("assignees")),
        "assignee_count": len(it.get("assignees") or []), "author_association": it.get("author_association"), "state_gh": it.get("state", "open"),
    }


def run_query(gh: GitHub, q: str, max_pages: int = 10, log=print) -> tuple[list[dict], int, bool]:
    """Fetch up to 1,000 results. Returns (items, total_count, incomplete)."""
    items: list[dict] = []
    total = 0
    incomplete = False
    for page in range(1, max_pages + 1):
        status, body = gh.search_issues(q, page=page, sort="updated")
        if status == 422:
            log(f"search 422 (query rejected): {q}")
            return items, -1, True
        if status != 200 or not isinstance(body, dict):
            log(f"search status {status}: {q}")
            break
        total = body.get("total_count", 0)
        incomplete = incomplete or bool(body.get("incomplete_results"))
        batch = body.get("items", [])
        items.extend(_item(i) for i in batch)
        if len(batch) < 100 or len(items) >= min(total, 1000):
            break
    return items, total, incomplete


def sliced(gh: GitHub, q: str, start: date, end: date, log=print, depth: int = 0, budget_calls: list[int] | None = None) -> list[dict]:
    """Recursively split the created: window until total_count < 1000."""
    budget_calls = budget_calls if budget_calls is not None else [0]
    full = f"{q} created:{start.isoformat()}..{end.isoformat()}"
    # Probe with one page first to learn total_count cheaply.
    status, body = gh.search_issues(full, per_page=100, page=1, sort="updated")
    budget_calls[0] += 1
    if status != 200 or not isinstance(body, dict):
        log(f"search status {status}: {full}")
        return []
    total = body.get("total_count", 0)
    if total < 1000 or (end - start).days <= 1 or depth > 12:
        if body.get("incomplete_results"):
            log(f"incomplete_results for {full}")
        items = [_item(i) for i in body.get("items", [])]
        pages = min(10, (min(total, 1000) + 99) // 100)
        for page in range(2, pages + 1):
            s, b = gh.search_issues(full, page=page, sort="updated")
            budget_calls[0] += 1
            if s != 200 or not isinstance(b, dict):
                break
            items.extend(_item(i) for i in b.get("items", []))
        return items
    mid = start + (end - start) / 2
    return sliced(gh, q, start, mid, log, depth + 1, budget_calls) + sliced(gh, q, mid + timedelta(days=1), end, log, depth + 1, budget_calls)


def discover_global(gh: GitHub, *, max_calls: int = 400, lookback_days: int = 730, log=print) -> list[dict]:
    """Candidate pool: unassigned, not linked, labelled, recently updated."""
    q = base_query(unassigned_only=True)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)
    calls = [0]
    out: list[dict] = []
    try:
        out = sliced(gh, q, start, end, log=log, budget_calls=calls)
    except RateLimited as e:
        log(f"global discovery stopped: {e}")
    log(f"global discovery: {len(out)} items in {calls[0]} search calls")
    if calls[0] > max_calls:
        log(f"warning: used {calls[0]} search calls (> {max_calls})")
    return out


def discover_org(gh: GitHub, login: str, log=print) -> list[dict]:
    """All open newcomer-labelled issues in an organisation (assigned ones included)."""
    q = f"org:{login} " + base_query(unassigned_only=False, updated_within_days=365, max_comments=None)
    items, total, incomplete = run_query(gh, q, log=log)
    if total >= 1000:
        log(f"org {login}: {total} results, truncated to 1000 (consider slicing)")
    return items
