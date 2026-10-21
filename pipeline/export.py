"""Export SQLite -> JSON for the site and the public API.

Outputs
  data/export/issues.json, repos.json, meta.json        (site build input, committed)
  site/public/data/issues/index.json + {lang}.json       (client-side shards, compact)
  site/public/api/v1/{issues,repos,orgs,programs,meta}.json (public API, versioned)
Never includes comment text, comment authors, emails or student names.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import CURATED, EXPORT, ROOT, SITE_DATA, now_iso, read_json, write_json

API_DIR = ROOT / "site" / "public" / "api" / "v1"
EVAL_RESULTS = ROOT / "eval" / "results.json"
DATA_VERSION = "v1"


def _slug(full_name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", full_name.lower().replace("/", "--"))


def load_eval() -> dict:
    base = {"done": False, "sample_date": None, "n": 0, "precision_claimed": None, "recall_claimed": None, "precision_open": None,
            "recall_open": None, "ci": None, "bar_met": False}
    if EVAL_RESULTS.exists():
        r = read_json(EVAL_RESULTS)
        base.update({k: r.get(k) for k in base if k in r})
        base["done"] = True
    return base


def export(conn: sqlite3.Connection, *, run_row: dict | None = None, grace_days: int = 14,
           export_dir: Path | None = None, site_data_dir: Path | None = None, api_dir: Path | None = None) -> dict:
    EXPORT_ = export_dir or EXPORT
    SITE_DATA_ = site_data_dir or SITE_DATA
    API_DIR_ = api_dir or API_DIR
    ev = load_eval()
    verified = bool(ev["done"] and ev["bar_met"])
    today = datetime.now(timezone.utc).date()

    repos = {}
    for r in conn.execute("SELECT * FROM repos WHERE opted_out = 0 AND archived = 0 AND disabled = 0 AND tier != 'excluded'"):
        r = dict(r)
        h = conn.execute("SELECT * FROM repo_health_snapshots WHERE repo_id = ? ORDER BY day DESC LIMIT 1", (r["id"],)).fetchone()
        first_seen = conn.execute("SELECT MIN(day) AS d FROM repo_health_snapshots WHERE repo_id = ?", (r["id"],)).fetchone()["d"]
        grace_over = bool(first_seen) and (today - datetime.fromisoformat(first_seen).date()).days >= grace_days
        health = None
        if h:
            h = dict(h)
            negative_hidden = not grace_over
            health = {
                "first_time_merge_rate": h["first_time_merge_rate"] if (h["first_time_prs_closed"] or 0) >= 10 and (grace_over or (h["first_time_merge_rate"] or 0) >= 0.3) else None,
                "first_time_prs_closed": h["first_time_prs_closed"] or 0,
                "median_first_response_hours": h["median_first_response_hours"] if (h["first_response_n"] or 0) >= 10 and (grace_over or (h["median_first_response_hours"] or 0) <= 168) else None,
                "first_response_n": h["first_response_n"] or 0,
                "setup_friction": h["setup_friction"] or "unknown", "setup_signals": [s for s, v in (("contributing", r["has_contributing"]), ("devcontainer", r["has_devcontainer"]), ("dockerfile", r["has_dockerfile"]), ("code_of_conduct", r["has_code_of_conduct"]), ("issue_template", r["has_issue_template"]), ("pr_template", r["has_pr_template"])) if v],
                "bot_pr_share_estimate": h["bot_pr_share_estimate"], "bot_pr_n": h["bot_pr_n"] or 0,
                "negative_metrics_visible": not negative_hidden,
            }
        repos[r["id"]] = {
            "full_name": r["full_name"], "owner": r["owner"], "name": r["name"], "slug": _slug(r["full_name"]), "description": r["description"],
            "language": r["language"], "topics": json.loads(r["topics_json"] or "[]"), "stars": r["stars"] or 0, "open_claimable": 0,
            "gsoc_org_slug": r["gsoc_org_slug"], "health": health, "ai_policy": r["ai_policy"] or "unknown", "ai_policy_source": r["ai_policy_source"],
            "restricted_first_time_prs": bool(r["restricted_first_time_prs"]), "last_maintainer_activity": r["last_maintainer_activity"],
            "claim_required": bool(json.loads(r["claimable_yml_json"] or "{}").get("claim_required")), "pushed_at": r["pushed_at"], "fetched_at": r["fetched_at"],
        }

    issues = []
    counts = defaultdict(int)
    for i in conn.execute("SELECT * FROM issues WHERE state_gh = 'open' ORDER BY updated_at DESC"):
        i = dict(i)
        repo = repos.get(i["repo_id"])
        if not repo:
            continue
        age = (today - datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")).date()).days if i["created_at"] else None
        state = i["claim_state"] or "open"
        counts[state] += 1
        if state == "open":
            repo["open_claimable"] += 1
        issues.append({
            "id": i["id"], "number": i["number"], "repo": repo["full_name"], "title": i["title"], "url": i["url"], "state": state,
            "verdict_verified": verified, "labels": json.loads(i["labels_json"] or "[]"), "language": repo["language"],
            "created_at": i["created_at"], "updated_at": i["updated_at"], "comments": i["comments_count"] or 0, "age_days": age,
            "evidence": json.loads(i["evidence_json"] or "[]"), "gsoc_org_slug": repo["gsoc_org_slug"], "fetched_at": i["fetched_at"],
        })

    repo_list = sorted(repos.values(), key=lambda r: (-r["open_claimable"], -r["stars"]))
    orgs_with = len({i["gsoc_org_slug"] for i in issues if i["gsoc_org_slug"] and i["state"] == "open"})
    meta = {
        "generated_at": now_iso(), "run_id": (run_row or {}).get("run_id"), "data_version": DATA_VERSION,
        "counts": {"repos": len(repo_list), "issues": len(issues), "open": counts["open"], "claimed": counts["claimed"], "stale_claim": counts["stale_claim"],
                   "restricted": counts["restricted"], "orgs_with_issues": orgs_with},
        "eval": ev, "quota": {k: (run_row or {}).get(k, 0) for k in ("rest_used", "graphql_used", "search_used")} if run_row else None,
    }

    write_json(EXPORT_ / "issues.json", issues, compact=True)
    write_json(EXPORT_ / "repos.json", repo_list, compact=True)
    write_json(EXPORT_ / "meta.json", meta)

    # Client shards (compact keys to keep the index small).
    def compact(i):
        return {"i": i["id"], "n": i["number"], "r": i["repo"], "t": i["title"], "u": i["url"], "s": i["state"], "l": i["labels"][:4], "g": i["language"],
                "c": i["created_at"][:10], "d": i["updated_at"][:10], "m": i["comments"], "e": i["evidence"], "o": i["gsoc_org_slug"], "f": i["fetched_at"]}
    by_lang = defaultdict(list)
    for i in issues:
        by_lang[(i["language"] or "other").lower()].append(compact(i))
    shard_dir = SITE_DATA_ / "issues"
    shard_dir.mkdir(parents=True, exist_ok=True)
    for old in shard_dir.glob("*.json"):
        old.unlink()
    index = {"generated_at": meta["generated_at"], "verified": verified, "languages": {}, "repos": {r["full_name"]: {"stars": r["stars"], "org": r["gsoc_org_slug"], "ai": r["ai_policy"], "slug": r["slug"], "h": (r["health"] or {}).get("first_time_merge_rate"), "rt": (r["health"] or {}).get("median_first_response_hours"), "cr": r["claim_required"]} for r in repo_list}}
    for lang, items in by_lang.items():
        fname = re.sub(r"[^a-z0-9.-]+", "-", lang.replace("++", "pp").replace("#", "sharp")) + ".json"
        write_json(shard_dir / fname, items, compact=True)
        index["languages"][lang] = {"file": fname, "count": len(items)}
    write_json(shard_dir / "index.json", index, compact=True)

    # Public API.
    API_DIR_.mkdir(parents=True, exist_ok=True)
    wrap = lambda data: {"version": DATA_VERSION, "generated_at": meta["generated_at"], "license": "CC BY 4.0", "source_of_truth": "https://github.com", "data": data}
    write_json(API_DIR_ / "issues.json", wrap(issues), compact=True)
    write_json(API_DIR_ / "repos.json", wrap(repo_list), compact=True)
    write_json(API_DIR_ / "meta.json", wrap(meta))
    if (EXPORT_ / "orgs.json").exists():
        orgs = read_json(EXPORT_ / "orgs.json")
        for o in orgs:
            o["open_claimable"] = sum(1 for i in issues if i["gsoc_org_slug"] == o["slug"] and i["state"] == "open")
        write_json(API_DIR_ / "orgs.json", wrap(orgs), compact=True)
        org_dir = API_DIR_ / "orgs"
        org_dir.mkdir(exist_ok=True)
        for o in orgs:
            write_json(org_dir / f"{o['slug']}.json", wrap({**o, "issues": [i for i in issues if i["gsoc_org_slug"] == o["slug"]][:200]}), compact=True)
    if (CURATED / "programs.json").exists():
        write_json(API_DIR_ / "programs.json", wrap(read_json(CURATED / "programs.json")["programs"]))
    return meta
