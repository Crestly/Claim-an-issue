"""Claimability classifier. Pure function; the rules here are mirrored word for
word on the site's /methodology page. Keep them in sync (tests check the
exported RULES text appears in site/src/pages/methodology.astro).

Input is a normalised dict (see `normalise_graphql_issue` in enrich.py):
  has_assignee, assignee_count
  linked_prs:   [{state: OPEN|CLOSED|MERGED, url, created_at}]  (closedByPullRequestsReferences)
  crossref_prs: [{state, url, created_at}]                       (timeline CROSS_REFERENCED_EVENT from PRs)
  comments:     [{author_key, author_association, is_bot, created_at, body, url}]  (body used in memory only)
  created_at, updated_at, labels, repo: {ai_policy, restricted_first_time_prs, claim_commands, newcomer_labels}
Output: dict(claim_state, evidence[], claim_comment_at, claim_pattern_id, claim_by_maintainer,
             maintainer_rebuttal_at, last_activity_at)
No comment text or author identity leaves this module.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

STALE_DAYS = 14
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
NEWCOMER_LABELS = {
    "good first issue", "good-first-issue", "goodfirstissue", "help wanted", "help-wanted", "up-for-grabs", "up for grabs",
    "first-timers-only", "first timers only", "beginner", "beginner friendly", "beginner-friendly", "easy", "e-easy",
    "difficulty: easy", "difficulty/easy", "low-hanging-fruit", "low hanging fruit", "newcomer", "starter", "good first bug",
    "d: easy", "d-easy", "level: easy", "effort: low", "contributor friendly", "jump in",
}

# Claim patterns. Each: (id, compiled regex, strength). "command" patterns must start the comment.
# Only `.take-issue` (Apache Beam) was verified on a real workflow before launch; the rest are tested by the blind eval.
CLAIM_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("cmd_assign", re.compile(r"^\s*/(assign(-me)?|take|claim|dibs)\b", re.I), "strong"),
    ("cmd_take_issue", re.compile(r"^\s*\.take-issue\b", re.I), "strong"),
    ("phrase_work_on", re.compile(r"\b(can|could|may|shall)\s+i\s+(please\s+)?(work|take|pick|have|try|handle)\b.{0,40}\b(this|it|that|issue|one|up|on)\b", re.I), "medium"),
    ("phrase_like_to", re.compile(r"\bi\s*(would|'d)\s+(like|love)\s+to\s+(work|take|try|pick|handle|contribute|give)\b", re.I), "medium"),
    ("phrase_will_take", re.compile(r"\bi\s*(will|'ll)\s+(take|work|pick|handle|try|do|give|fix|implement|look into|start|tackle)\b", re.I), "medium"),
    ("phrase_working_on", re.compile(r"\b(i\s*(am|'m)\s+)?(currently\s+)?working\s+on\s+(this|it|that|the\s+(issue|fix|pr))\b", re.I), "medium"),
    ("phrase_want_to", re.compile(r"\bi\s+(want|wish|intend|plan)\s+to\s+(work|take|try|pick|fix|contribute)\b", re.I), "medium"),
    ("phrase_assign_me", re.compile(r"\b(please\s+)?assign\s+(this|it|me|the\s+issue)\b|\bassign(ed)?\s+(this\s+)?to\s+me\b|\bcan\s+(you|someone|i)\s+(please\s+)?(be\s+)?assign", re.I), "medium"),
    ("phrase_pick_up", re.compile(r"\b(i\s*(will|'ll|can|am going to)\s+)?pick(ing)?\s+(this|it)\s+up\b|\bi\s+can\s+(take|do|handle|fix)\s+(this|it|that)\b", re.I), "medium"),
    ("phrase_give_try", re.compile(r"\b(give|take)\s+(this|it)\s+a\s+(try|shot|go)\b", re.I), "medium"),
    ("question_available", re.compile(r"\bis\s+(this|it|the\s+issue)\s+(still\s+)?(available|open|free|up\s+for\s+grabs|unassigned|being\s+worked)", re.I), "weak"),
]
RELEASE_PATTERNS = re.compile(
    r"^\s*/unassign\b|\b(no\s+longer|not)\s+(be\s+)?working\s+on\s+(this|it)\b|\bi\s*(can'?t|cannot|won'?t|am\s+unable\s+to)\s+(work|continue|take|do)\b|"
    r"\bplease\s+unassign\b|\bfeel\s+free\s+to\s+take\s+(it\s+)?over\b|\bsomeone\s+else\s+can\s+(take|pick)\b", re.I)
REBUTTAL_PATTERNS = re.compile(
    r"\b(already\s+(taken|assigned|claimed|being\s+worked|in\s+progress|has\s+a\s+pr|have\s+a\s+pr))\b|\bsomeone\s+(else\s+)?is\s+(already\s+)?working\b|"
    r"\bnot\s+(available|open|accepting)\b|\b(we|i)\s+don'?t\s+assign\b|\bno\s+need\s+to\s+(ask|claim)\b|\bplease\s+(don'?t|do\s+not)\s+(claim|ask)\b|"
    r"\bthis\s+(is|was)\s+(a\s+)?duplicate\b|\bclosing\b|\bnot\s+a\s+good\s+first\b|\bassigned\s+to\s+@?\w+\b(?!\s+you)", re.I)
CONFIRM_PATTERNS = re.compile(r"\b(go\s+ahead|all\s+yours|it'?s\s+yours|assigned\s+(it\s+)?to\s+you|feel\s+free|sure[,.!]|sounds\s+good|thanks?\s+for\s+(taking|picking)|go\s+for\s+it|you\s+got\s+it)\b", re.I)

RULES = """\
Claimed: an assignee, or an open linked or cross-referenced pull request, or a claim comment with no maintainer rebuttal.
Stale claim ("may be free again"): a claim comment or assignee with no pull request and no activity for 14 days. A heuristic; we show the evidence and never imply it is free.
Open: none of the above.
Restricted: the repository's AI policy forbids AI use on good first issues, or the repository limits first-time pull requests.\
"""


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z") if dt else None


def match_claim(body: str, extra_commands: list[str] | None = None) -> tuple[str, str] | None:
    """Return (pattern_id, strength) if body looks like a claim. Body never leaves the caller."""
    if not body:
        return None
    text = body.strip()
    # Ignore quoted replies and code blocks.
    text = re.sub(r"(?m)^>.*$", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    if len(text) > 2000:
        text = text[:2000]
    for cmd in extra_commands or []:
        if cmd and re.match(r"^\s*" + re.escape(cmd) + r"\b", text, re.I):
            return ("cmd_repo_custom", "strong")
    for pid, rx, strength in CLAIM_PATTERNS:
        if rx.search(text):
            return (pid, strength)
    return None


def is_release(body: str) -> bool:
    return bool(body) and bool(RELEASE_PATTERNS.search(body))


def classify(issue: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    repo = issue.get("repo") or {}
    evidence: list[dict] = []
    created = _parse(issue.get("created_at"))
    updated = _parse(issue.get("updated_at")) or created or now
    last_activity = updated

    # ---- assignee
    has_assignee = bool(issue.get("has_assignee"))
    if has_assignee:
        n = issue.get("assignee_count") or 1
        evidence.append({"kind": "assignee", "detail": f"Assigned to {n} {'person' if n == 1 else 'people'} on GitHub"})

    # ---- linked / cross-referenced PRs
    open_prs = [p for p in issue.get("linked_prs", []) if p.get("state") == "OPEN"]
    merged_prs = [p for p in issue.get("linked_prs", []) if p.get("state") == "MERGED"]
    closed_prs = [p for p in issue.get("linked_prs", []) if p.get("state") == "CLOSED"]
    xref_open = [p for p in issue.get("crossref_prs", []) if p.get("state") == "OPEN"]
    for p in open_prs[:3]:
        evidence.append({"kind": "linked_pr", "detail": "Open pull request linked to this issue", "url": p.get("url"), "at": p.get("created_at")})
        last_activity = max(last_activity, _parse(p.get("created_at")) or last_activity)
    for p in xref_open[:3]:
        evidence.append({"kind": "cross_ref_pr", "detail": "Open pull request references this issue", "url": p.get("url"), "at": p.get("created_at")})
        last_activity = max(last_activity, _parse(p.get("created_at")) or last_activity)
    if closed_prs and not open_prs:
        evidence.append({"kind": "linked_pr", "detail": f"{len(closed_prs)} linked pull request(s) were closed without merging; a previous attempt may have been abandoned"})
    if merged_prs:
        evidence.append({"kind": "linked_pr", "detail": "A linked pull request was merged (issue may be effectively done)", "url": merged_prs[-1].get("url")})

    # ---- comments: claim, release, rebuttal, first maintainer response
    comments = sorted((c for c in issue.get("comments", []) if not c.get("is_bot")), key=lambda c: c.get("created_at") or "")
    claim_at: datetime | None = None
    claim_pid: str | None = None
    claim_strength: str | None = None
    claim_author: str | None = None
    claim_by_maintainer = False
    claim_url: str | None = None
    rebuttal_at: datetime | None = None
    confirm_at: datetime | None = None
    first_maint_resp: datetime | None = None
    extra_cmds = repo.get("claim_commands") or []
    for c in comments:
        ts = _parse(c.get("created_at"))
        if ts:
            last_activity = max(last_activity, ts)
        assoc = (c.get("author_association") or "NONE").upper()
        body = c.get("body") or ""
        if assoc in MAINTAINER and first_maint_resp is None and ts and created and ts > created:
            first_maint_resp = ts
        if claim_at and c.get("author_key") == claim_author and is_release(body):
            evidence.append({"kind": "claim_comment", "detail": "The person who claimed later said they are no longer working on it", "url": c.get("url"), "at": c.get("created_at")})
            claim_at = claim_pid = claim_strength = claim_author = None
            claim_by_maintainer = False
            continue
        if claim_at and assoc in MAINTAINER and c.get("author_key") != claim_author and ts and ts > claim_at:
            if REBUTTAL_PATTERNS.search(body):
                rebuttal_at = ts
                evidence.append({"kind": "maintainer_rebuttal", "detail": "A maintainer replied after the claim indicating it is not available or not assigned to the claimant", "url": c.get("url"), "at": c.get("created_at")})
                claim_at = claim_pid = claim_strength = claim_author = None
                continue
            if CONFIRM_PATTERNS.search(body):
                confirm_at = ts
        m = match_claim(body, extra_cmds)
        if m and not (assoc in MAINTAINER and m[1] == "weak"):
            claim_at, claim_pid, claim_strength = ts, m[0], m[1]
            claim_author = c.get("author_key")
            claim_by_maintainer = assoc in MAINTAINER
            claim_url = c.get("url")
            rebuttal_at = None
    if claim_at:
        who = "a maintainer" if claim_by_maintainer else "a contributor"
        what = {"strong": "used a claim command", "medium": "said they would work on it", "weak": "asked whether it is still available"}[claim_strength or "medium"]
        evidence.append({"kind": "claim_comment", "detail": f"On {claim_at.date().isoformat()} {who} {what} (pattern {claim_pid}); no maintainer rebuttal seen", "url": claim_url, "at": _iso(claim_at)})
        if confirm_at and confirm_at > claim_at:
            evidence.append({"kind": "claim_comment", "detail": "A maintainer appears to have confirmed the claim", "at": _iso(confirm_at)})

    # ---- restrictions
    labels = {l.lower() for l in issue.get("labels", [])}
    newcomer = {l.lower() for l in (repo.get("newcomer_labels") or [])} | NEWCOMER_LABELS
    restricted = False
    if repo.get("ai_policy") == "forbids-gfi" and labels & newcomer:
        restricted = True
        evidence.append({"kind": "ai_policy", "detail": "This repository forbids AI assistance on beginner issues; read its policy before starting"})
    elif repo.get("ai_policy") == "forbids":
        evidence.append({"kind": "ai_policy", "detail": "This repository does not accept AI-generated contributions"})
    if repo.get("restricted_first_time_prs"):
        restricted = True
        evidence.append({"kind": "first_time_restriction", "detail": "This repository limits pull requests from first-time contributors"})

    # ---- decide
    idle_days = (now - last_activity).days if last_activity else 0
    if open_prs or xref_open:
        state = "claimed"
    elif has_assignee or claim_at:
        if idle_days >= STALE_DAYS:
            state = "stale_claim"
            evidence.append({"kind": "stale", "detail": f"No pull request and no activity for {idle_days} days since the claim or assignment; it may be free again. Ask before starting."})
        else:
            state = "claimed"
    else:
        state = "open"
    if restricted and state in ("open", "stale_claim"):
        state = "restricted"

    return {
        "claim_state": state,
        "evidence": evidence,
        "claim_comment_at": _iso(claim_at),
        "claim_pattern_id": claim_pid,
        "claim_by_maintainer": int(claim_by_maintainer),
        "maintainer_rebuttal_at": _iso(rebuttal_at),
        "last_activity_at": _iso(last_activity),
        "first_maintainer_response_at": _iso(first_maint_resp),
        "idle_days": idle_days,
    }
