"""Pipeline orchestrator.

  python pipeline/run.py refresh   [--data-dir PATH] [--max-search-calls N] [--max-issue-batches N] [--max-health-repos N] [--orgs-only]
  python pipeline/run.py fixture   --fixtures pipeline/tests/fixtures --out /tmp/claimable-fixture   (no network)
  python pipeline/run.py sample-eval [--n 200]
  python pipeline/run.py restore-test --data-dir PATH
  python pipeline/run.py verify-mapping

Environment: CLAIMABLE_PAT (fine-grained personal access token; read-only on public repos).
Every external call and its limit is documented in docs/LIMITS.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classify import classify  # noqa: E402
from common import CURATED, DATA, EXPORT, ROOT, env, now_iso, read_json, today, write_json  # noqa: E402
from db import connect, upsert  # noqa: E402
from discover import discover_global, discover_org  # noqa: E402
from enrich import fetch_issues, fetch_repos, normalise_graphql_issue, normalise_repo  # noqa: E402
from export import export  # noqa: E402
from github_api import Budget, GitHub, RateLimited  # noqa: E402
from health import compute as compute_health, fetch_health, setup_friction  # noqa: E402
from snapshot import dump, restore  # noqa: E402

LOG: list[str] = []


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}"
    LOG.append(line)
    print(line, flush=True)


# ----------------------------------------------------------------- curated data
def load_curated(conn: sqlite3.Connection) -> tuple[list[dict], dict[str, str], set[str]]:
    """Load orgs, mapping, programs, opt-outs into the DB. Returns (orgs, login->slug, optout targets)."""
    orgs = read_json(EXPORT / "orgs.json") if (EXPORT / "orgs.json").exists() else []
    ts = now_iso()
    for o in orgs:
        upsert(conn, "orgs", {"slug": o["slug"], "name": o["name"], "category": o["category"], "url": o["url"], "ideas_url": o["ideas_url"],
                              "guide_url": o["guide_url"], "chat_url": o["chat_url"], "mailing_list": o["mailing_list"],
                              "topics_json": json.dumps(o["topics"]), "technologies_json": json.dumps(o["technologies"]),
                              "first_year": o["first_year"], "last_year": o["last_year"], "years_count": o["years_count"],
                              "total_projects": o["total_projects"], "source": o["source"], "fetched_at": o["fetched_at"], "last_verified": o.get("last_verified")}, ["slug"])
        for y, d in o["years"].items():
            upsert(conn, "org_years", {"org_slug": o["slug"], "year": int(y), "num_projects": d["num_projects"], "projects_url": d["projects_url"],
                                       "source": o["source"], "fetched_at": o["fetched_at"], "last_verified": None}, ["org_slug", "year"])
        for a in o["aliases"]:
            upsert(conn, "org_aliases", {"alias": a, "org_slug": o["slug"], "source": o["source"], "fetched_at": o["fetched_at"], "last_verified": None}, ["alias"])
        for g in o["github_orgs"]:
            upsert(conn, "org_github_map", {"org_slug": o["slug"], "github_login": g, "kind": None, "mapping_source": o["github_source"],
                                            "verified": 0, "source": "curated", "fetched_at": ts, "last_verified": None}, ["org_slug", "github_login"])
    login_to_slug = {}
    for r in conn.execute("SELECT org_slug, github_login FROM org_github_map"):
        login_to_slug.setdefault(r["github_login"].lower(), r["org_slug"])

    programs = read_json(CURATED / "programs.json")["programs"] if (CURATED / "programs.json").exists() else []
    for p in programs:
        upsert(conn, "programs", {"id": p["id"], "name": p["name"], "short": p["short"], "official_url": p["official_url"], "timeline_url": p["timeline_url"],
                                  "eligibility_url": p["eligibility_url"], "audience": p["audience"], "status": p["status"], "source": "curated", "fetched_at": ts,
                                  "last_verified": p["last_verified"]}, ["id"])
        for e in p["events"]:
            upsert(conn, "program_dates", {"program_id": p["id"], "start": e["start"], "end": e["end"], "title": e["title"], "kind": e["kind"], "status": e["status"],
                                           "source": "curated", "fetched_at": ts, "last_verified": p["last_verified"]}, ["program_id", "start", "title"])

    optouts = read_json(CURATED / "optouts.json")["optouts"] if (CURATED / "optouts.json").exists() else []
    targets = set()
    for o in optouts:
        upsert(conn, "optouts", {"target": o["target"].lower(), "method": o["method"], "requested_at": o["requested_at"], "applied_at": o.get("applied_at"),
                                 "note": o.get("note", ""), "source": "curated", "fetched_at": ts, "last_verified": o.get("applied_at")}, ["target"])
        targets.add(o["target"].lower())
    conn.commit()
    return orgs, login_to_slug, targets


# ------------------------------------------------------------- repo filtering
def keep_repo(r: dict, *, is_gsoc: bool) -> tuple[bool, str]:
    if r["opted_out"]:
        return False, "opted_out"
    if r["archived"] or r["disabled"]:
        return False, "archived"
    if r["is_fork"] and not is_gsoc:
        return False, "fork"
    # Same heuristic goodfirstissue.org publishes: >1000 open issues AND <100 stars is almost always automated reports.
    if (r["open_issues"] or 0) > 1000 and (r["stars"] or 0) < 100:
        return False, "issue_flood"
    if r["pushed_at"]:
        pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - pushed > timedelta(days=180):
            return False, "inactive_180d"
    return True, "ok"


def tier_for(r: dict, *, is_gsoc: bool) -> str:
    pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) if r.get("pushed_at") else None
    if pushed and datetime.now(timezone.utc) - pushed > timedelta(days=60):
        return "cold"
    if is_gsoc or (r.get("stars") or 0) >= 2000:
        return "hot"
    return "warm"


# ------------------------------------------------------------- core processing
def process_issue(conn: sqlite3.Connection, repo_row: dict, norm: dict, *, day: str, now: datetime) -> str:
    """Classify, upsert issue + snapshot, derive claim_events. Returns new state."""
    res = classify(norm, now)
    prev = conn.execute("SELECT claim_state, state_gh, linked_pr_open, linked_pr_merged FROM issues WHERE id = ?", (norm["id"],)).fetchone()
    linked = norm["linked_prs"]
    row = {
        "id": norm["id"], "node_id": norm["node_id"], "repo_id": repo_row["id"], "number": norm["number"], "title": norm["title"][:300], "url": norm["url"],
        "state_gh": norm["state_gh"], "labels_json": json.dumps(norm["labels"]), "created_at": norm["created_at"], "updated_at": norm["updated_at"],
        "closed_at": norm["closed_at"], "comments_count": norm["comments_count"], "has_assignee": int(norm["has_assignee"]), "assignee_count": norm["assignee_count"],
        "linked_pr_open": sum(1 for p in linked if p["state"] == "OPEN"), "linked_pr_closed": sum(1 for p in linked if p["state"] == "CLOSED"),
        "linked_pr_merged": sum(1 for p in linked if p["state"] == "MERGED"), "crossref_pr_open": sum(1 for p in norm["crossref_prs"] if p["state"] == "OPEN"),
        "claim_comment_at": res["claim_comment_at"], "claim_pattern_id": res["claim_pattern_id"], "claim_by_maintainer": res["claim_by_maintainer"],
        "maintainer_rebuttal_at": res["maintainer_rebuttal_at"], "last_activity_at": res["last_activity_at"], "claim_state": res["claim_state"],
        "evidence_json": json.dumps(res["evidence"]), "first_maintainer_response_at": res["first_maintainer_response_at"],
        "author_is_first_timer": norm["author_is_first_timer"], "source": "github:graphql", "fetched_at": now_iso(), "last_verified": now_iso(),
    }
    upsert(conn, "issues", row, ["id"])
    upsert(conn, "issue_snapshots", {"issue_id": norm["id"], "day": day, "claim_state": res["claim_state"], "state_gh": norm["state_gh"],
                                     "has_assignee": row["has_assignee"], "linked_pr_open": row["linked_pr_open"], "linked_pr_merged": row["linked_pr_merged"],
                                     "comments_count": row["comments_count"], "source": "derived", "fetched_at": now_iso(), "last_verified": None}, ["issue_id", "day"])
    if prev:
        at = now_iso()
        events = []
        if prev["claim_state"] != res["claim_state"]:
            if res["claim_state"] in ("claimed",) and prev["claim_state"] in ("open", "stale_claim", "restricted"):
                events.append("claimed")
            elif res["claim_state"] in ("open", "restricted") and prev["claim_state"] in ("claimed", "stale_claim"):
                events.append("unclaimed")
            elif res["claim_state"] == "stale_claim":
                events.append("stale")
        if (prev["linked_pr_open"] or 0) == 0 and row["linked_pr_open"] > 0:
            events.append("pr_opened")
        if (prev["linked_pr_merged"] or 0) == 0 and row["linked_pr_merged"] > 0:
            events.append("pr_merged")
        if prev["state_gh"] == "open" and norm["state_gh"] == "closed":
            events.append("closed")
        if prev["state_gh"] == "closed" and norm["state_gh"] == "open":
            events.append("reopened")
        for ev in events:
            conn.execute("INSERT OR IGNORE INTO claim_events (issue_id, at, event, from_state, to_state, source, fetched_at) VALUES (?,?,?,?,?,?,?)",
                         (norm["id"], at, ev, prev["claim_state"], res["claim_state"], "derived", at))
    return res["claim_state"]


# --------------------------------------------------------------------- refresh
def cmd_refresh(args) -> int:
    token = env("CLAIMABLE_PAT") or env("GITHUB_TOKEN")
    if not token:
        log("no CLAIMABLE_PAT set; refusing to run unauthenticated (60 req/h is useless). See NEEDS_OWNER.md")
        return 2
    run_id = f"{today()}-{uuid.uuid4().hex[:6]}"
    started = now_iso()
    conn = connect()
    data_dir = Path(args.data_dir) if args.data_dir else None
    if data_dir and data_dir.exists():
        counts = restore(conn, data_dir, days=45)
        log(f"restored from {data_dir}: {counts}")
    orgs, login_to_slug, optout_targets = load_curated(conn)
    budget = Budget(rest_floor=400, graphql_floor=400)
    gh = GitHub(token, budget, verbose=args.verbose)
    try:
        gh.rate_limit()
    except RateLimited as e:
        log(f"rate_limit probe: {e}")
    # GITHUB_TOKEN is 1,000 req/h. A 400-remaining floor leaves almost nothing to do.
    if (budget.rest_remaining or 5000) < 2000:
        budget.rest_floor = 80
        budget.graphql_floor = 80
        log(f"low quota token: floors set to 80 (rest={budget.rest_remaining} graphql={budget.graphql_remaining})")
    log(f"start {run_id}; quota rest={budget.rest_remaining} graphql={budget.graphql_remaining}")
    day = today()
    now = datetime.now(timezone.utc)

    # 1. verify org -> GitHub mapping (cheap, batched)
    verify_mapping(conn, gh)

    # 2. discovery
    discovered: dict[str, dict] = {}
    logins = [r["github_login"] for r in conn.execute("SELECT DISTINCT github_login FROM org_github_map WHERE verified >= 0 ORDER BY github_login")]
    search_calls = 0
    for login in logins:
        if search_calls >= args.max_search_calls:
            log("search budget reached during org discovery")
            break
        try:
            items = discover_org(gh, login, log=log)
        except RateLimited as e:
            log(f"stopped org discovery: {e}")
            break
        search_calls += max(1, (len(items) + 99) // 100)
        for it in items:
            discovered[f"{it['repo_full_name'].lower()}#{it['number']}"] = it
    log(f"org discovery: {len(discovered)} issues from {len(logins)} logins ({search_calls} calls)")
    if not args.orgs_only and search_calls < args.max_search_calls:
        try:
            for it in discover_global(gh, max_calls=args.max_search_calls - search_calls, log=log):
                discovered.setdefault(f"{it['repo_full_name'].lower()}#{it['number']}", it)
        except RateLimited as e:
            log(f"stopped global discovery: {e}")
    log(f"discovery total: {len(discovered)} candidate issues")

    # 3. repositories
    tracked = {f"{r['full_name'].lower()}#{r['number']}": (r["full_name"], r["number"]) for r in conn.execute(
        "SELECT repos.full_name, issues.number FROM issues JOIN repos ON repos.id = issues.repo_id WHERE issues.state_gh = 'open'")}
    repo_names = sorted({v["repo_full_name"] for v in discovered.values()} | {v[0] for v in tracked.values()}, key=str.lower)
    org_of = {}
    for fn in repo_names:
        org_of[fn.lower()] = login_to_slug.get(fn.split("/")[0].lower())
    log(f"fetching {len(repo_names)} repositories")
    repo_rows: dict[str, dict] = {}
    skipped: dict[str, int] = {}
    try:
        for r in fetch_repos(gh, repo_names, opted_out_targets=optout_targets, org_of=org_of, log=log):
            is_gsoc = bool(r["gsoc_org_slug"])
            ok, why = keep_repo(r, is_gsoc=is_gsoc)
            r["tier"] = tier_for(r, is_gsoc=is_gsoc) if ok else "excluded"
            if r["opted_out"]:
                conn.execute("DELETE FROM issues WHERE repo_id = ?", (r["id"],))
            upsert(conn, "repos", r, ["id"])
            if ok:
                repo_rows[r["full_name"].lower()] = r
            else:
                skipped[why] = skipped.get(why, 0) + 1
    except (RateLimited, RuntimeError) as e:
        log(f"repo fetch stopped: {e}")
    conn.commit()
    log(f"repos kept {len(repo_rows)}, skipped {skipped}")

    # 4. issues (hot repos first, then warm; cold weekly)
    weekday = now.weekday()
    refs: list[tuple[str, int]] = []
    order = {"hot": 0, "warm": 1, "cold": 2}
    all_refs = {**{k: (v["repo_full_name"], v["number"]) for k, v in discovered.items()}, **tracked}
    for key, (fn, num) in all_refs.items():
        rr = repo_rows.get(fn.lower())
        if not rr:
            continue
        if rr["tier"] == "cold" and weekday != 6:
            continue
        refs.append((fn, num))
    refs.sort(key=lambda t: (order.get(repo_rows[t[0].lower()]["tier"], 9), t[0].lower(), t[1]))
    log(f"enriching {len(refs)} issues")
    seen = 0
    states: dict[str, int] = {}
    try:
        for fn, norm in fetch_issues(gh, refs[: args.max_issue_batches * 50], repo_rows, log=log):
            st = process_issue(conn, repo_rows[fn.lower()], norm, day=day, now=now)
            states[st] = states.get(st, 0) + 1
            seen += 1
            if seen % 500 == 0:
                conn.commit()
                log(f"  {seen} issues; graphql remaining {budget.graphql_remaining}")
    except (RateLimited, RuntimeError) as e:
        log(f"enrichment stopped: {e}")
    conn.commit()
    log(f"issues processed {seen}: {states}")

    # 5. health (hot first, then least-recently measured)
    cands = [dict(r) for r in conn.execute(
        "SELECT repos.*, (SELECT MAX(day) FROM repo_health_snapshots h WHERE h.repo_id = repos.id) AS last_day FROM repos "
        "WHERE opted_out = 0 AND archived = 0 ORDER BY CASE tier WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END, last_day IS NOT NULL, last_day, stars DESC")]
    done = 0
    try:
        for r in cands:
            if done >= args.max_health_repos:
                break
            if r["last_day"] == day:
                continue
            if r["tier"] != "hot" and r["last_day"] and (datetime.fromisoformat(day) - datetime.fromisoformat(r["last_day"])).days < 7:
                continue
            h = fetch_health(gh, r, log=log)
            if h:
                h["open_claimable"] = conn.execute("SELECT COUNT(*) FROM issues WHERE repo_id = ? AND state_gh = 'open' AND claim_state = 'open'", (r["id"],)).fetchone()[0]
                upsert(conn, "repo_health_snapshots", h, ["repo_id", "day"])
                done += 1
    except (RateLimited, RuntimeError) as e:
        log(f"health stopped: {e}")
    conn.commit()
    log(f"health measured for {done} repos")

    # 6. finish (always write what we have, even if a stage raised)
    run_row = {"run_id": run_id, "started_at": started, "finished_at": now_iso(), "rest_used": budget.rest_used, "graphql_used": budget.graphql_used,
               "search_used": budget.search_used, "repos_refreshed": len(repo_rows), "issues_seen": seen, "errors": budget.errors, "notes": json.dumps(skipped)}
    upsert(conn, "runs", run_row, ["run_id"])
    conn.commit()
    meta = export(conn, run_row=run_row)
    log(f"exported: {meta['counts']}")
    if data_dir:
        counts = dump(conn, data_dir, day)
        log(f"snapshot dump -> {data_dir}: {counts}")
    write_json(DATA / "last_run.json", {"run": run_row, "quota": budget.summary(), "log": LOG[-200:]})
    return 0


def verify_mapping(conn: sqlite3.Connection, gh: GitHub) -> None:
    """Check that each mapped GitHub login exists and whether it is an org or a user. ~1 point per 100 logins."""
    rows = [r for r in conn.execute("SELECT org_slug, github_login FROM org_github_map WHERE verified = 0")]
    if not rows:
        return
    logins = sorted({r["github_login"] for r in rows})
    found: dict[str, str | None] = {}
    for i in range(0, len(logins), 100):
        chunk = logins[i:i + 100]
        q = "query { " + " ".join(f'o{j}: repositoryOwner(login: {json.dumps(l)}) {{ __typename login }}' for j, l in enumerate(chunk)) + " }"
        try:
            data = gh.graphql(q).get("data") or {}
        except (RuntimeError, RateLimited) as e:
            log(f"mapping verification error: {e}")
            return
        for j, l in enumerate(chunk):
            node = data.get(f"o{j}")
            found[l.lower()] = (node or {}).get("__typename")
    ts = now_iso()
    bad = []
    for r in rows:
        kind = found.get(r["github_login"].lower())
        if kind:
            conn.execute("UPDATE org_github_map SET verified = 1, kind = ?, last_verified = ? WHERE org_slug = ? AND github_login = ?",
                         (kind.lower(), ts, r["org_slug"], r["github_login"]))
        else:
            conn.execute("UPDATE org_github_map SET verified = -1, last_verified = ? WHERE org_slug = ? AND github_login = ?", (ts, r["org_slug"], r["github_login"]))
            bad.append(f"{r['org_slug']} -> {r['github_login']}")
    conn.commit()
    out = [dict(r) for r in conn.execute("SELECT org_slug, github_login, kind, verified, last_verified FROM org_github_map")]
    write_json(EXPORT / "org_github_verified.json", out)
    log(f"mapping verified: {len(rows) - len(bad)} ok, {len(bad)} missing{': ' + ', '.join(bad[:10]) if bad else ''}")


# --------------------------------------------------------------------- fixture
def cmd_fixture(args) -> int:
    """Run the whole post-network pipeline on recorded GraphQL fixtures. Writes outside the repo by default."""
    fx = Path(args.fixtures)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "fixture.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    load_curated(conn)
    repos_payload = read_json(fx / "repos_graphql.json")
    issues_payload = read_json(fx / "issues_graphql.json")
    prs_payload = read_json(fx / "prs_graphql.json") if (fx / "prs_graphql.json").exists() else {}
    org_of = {"llvm/llvm-project": "llvm-compiler-infrastructure", "zulip/zulip": "zulip", "sympy/sympy": "sympy"}
    repo_rows = {}
    for alias, node in repos_payload["data"].items():
        if alias == "rateLimit" or not node:
            continue
        r = normalise_repo(node, opted_out_targets=set(), org_slug=org_of.get(node["nameWithOwner"].lower()))
        ok, why = keep_repo(r, is_gsoc=bool(r["gsoc_org_slug"]))
        r["tier"] = tier_for(r, is_gsoc=bool(r["gsoc_org_slug"])) if ok else "excluded"
        upsert(conn, "repos", r, ["id"])
        if ok:
            repo_rows[r["full_name"].lower()] = r
    now = datetime.fromisoformat(issues_payload.get("_now", now_iso()).replace("Z", "+00:00"))
    day = now.date().isoformat()
    states = {}
    for alias, node in issues_payload["data"].items():
        if alias == "rateLimit" or not node or not node.get("issue"):
            continue
        fn = node["_repo"].lower()
        if fn not in repo_rows:
            states["skipped_repo"] = states.get("skipped_repo", 0) + 1
            continue
        norm = normalise_graphql_issue(node["issue"], repo_rows[fn])
        st = process_issue(conn, repo_rows[fn], norm, day=day, now=now)
        states[st] = states.get(st, 0) + 1
    for fn, payload in prs_payload.items():
        r = repo_rows.get(fn.lower())
        if not r:
            continue
        prs = payload["data"]["repository"]["pullRequests"]["nodes"]
        h = compute_health(prs)
        h.update({"repo_id": r["id"], "day": day, "setup_friction": setup_friction(r), "open_claimable": 0, "source": "fixture", "fetched_at": now_iso(), "last_verified": None})
        upsert(conn, "repo_health_snapshots", h, ["repo_id", "day"])
    conn.commit()
    run_row = {"run_id": f"fixture-{day}", "rest_used": 0, "graphql_used": 0, "search_used": 0}
    meta = export(conn, run_row=run_row, export_dir=out / "export", site_data_dir=out / "site-data", api_dir=out / "api")
    # Idempotency check: run the issue processing again and verify no duplicate snapshots/events.
    before = (conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0], conn.execute("SELECT COUNT(*) FROM claim_events").fetchone()[0])
    for alias, node in issues_payload["data"].items():
        if alias == "rateLimit" or not node or not node.get("issue"):
            continue
        fn = node["_repo"].lower()
        if fn not in repo_rows:
            continue
        process_issue(conn, repo_rows[fn], normalise_graphql_issue(node["issue"], repo_rows[fn]), day=day, now=now)
    after = (conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0], conn.execute("SELECT COUNT(*) FROM claim_events").fetchone()[0])
    dumped = dump(conn, out / "data-branch", day)
    conn2 = connect(out / "restored.sqlite")
    restored = restore(conn2, out / "data-branch")
    print(json.dumps({"states": states, "counts": meta["counts"], "idempotent": before == after, "dumped": dumped, "restored": restored}, indent=1))
    return 0 if before == after else 1


# ------------------------------------------------------------------ sample-eval
def cmd_sample_eval(args) -> int:
    """Stratified blind sample: by repo size (stars tercile) x classifier state, WITHOUT the verdict in the file."""
    conn = connect()
    rows = [dict(r) for r in conn.execute("SELECT issues.id, issues.url, issues.claim_state, repos.stars FROM issues JOIN repos ON repos.id = issues.repo_id WHERE issues.state_gh = 'open' AND repos.opted_out = 0")]
    if len(rows) < args.n:
        print(f"only {len(rows)} issues in DB; run refresh first")
        return 1
    stars = sorted(r["stars"] or 0 for r in rows)
    t1, t2 = stars[len(stars) // 3], stars[2 * len(stars) // 3]
    def bucket(r):
        s = r["stars"] or 0
        return ("small" if s < t1 else "medium" if s < t2 else "large", r["claim_state"])
    strata: dict[tuple, list] = {}
    for r in rows:
        strata.setdefault(bucket(r), []).append(r)
    rnd = random.Random(args.seed)
    per = max(1, args.n // len(strata))
    sample = []
    for k, items in strata.items():
        rnd.shuffle(items)
        sample.extend(items[:per])
    rest = [r for r in rows if r not in sample]
    rnd.shuffle(rest)
    sample.extend(rest[: args.n - len(sample)])
    rnd.shuffle(sample)
    out = ROOT / "eval" / f"sample_{today()}.csv"
    hidden = ROOT / "eval" / f".hidden_{today()}.json"  # classifier labels kept separately, read only by score.py
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_url", "human_label", "notes"])
        for r in sample:
            w.writerow([r["url"], "", ""])
    write_json(hidden, {r["url"]: r["claim_state"] for r in sample})
    print(f"wrote {out} ({len(sample)} rows). Label the human_label column with open|claimed|stale_claim|restricted|unsure WITHOUT looking at the site. Then run eval/score.py.")
    return 0


# ----------------------------------------------------------------- restore-test
def cmd_restore_test(args) -> int:
    d = Path(args.data_dir)
    conn = connect(Path(args.out) if args.out else d / "restore-test.sqlite")
    counts = restore(conn, d)
    print(json.dumps(counts))
    return 0 if sum(counts.values()) > 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("refresh")
    p.add_argument("--data-dir")
    p.add_argument("--max-search-calls", type=int, default=500)
    p.add_argument("--max-issue-batches", type=int, default=600)  # 600 x 50 = 30k issues, ~2,400 points
    p.add_argument("--max-health-repos", type=int, default=400)
    p.add_argument("--orgs-only", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(fn=cmd_refresh)
    p = sub.add_parser("fixture")
    p.add_argument("--fixtures", default=str(ROOT / "pipeline" / "tests" / "fixtures"))
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_fixture)
    p = sub.add_parser("sample-eval")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=20261021)
    p.set_defaults(fn=cmd_sample_eval)
    p = sub.add_parser("restore-test")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_restore_test)
    p = sub.add_parser("verify-mapping")
    p.set_defaults(fn=lambda a: (verify_mapping(connect(), GitHub(env("CLAIMABLE_PAT"))) or 0))
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
