"""Build the derived GSoC organisation table from the community dataset.

Input : data/raw/gsoc/{2016..2026}.json (fetched, not committed)
        data/curated/org_aliases.csv      (alias -> canonical name)
        data/curated/org_github_map.csv   (manual GitHub org mapping/overrides)
Output: data/export/orgs.json             (our derived fields only)
        data/export/org_years.json        (year -> org slugs)
        data/export/org_github_review.csv (heuristic candidates for manual review)

Deliberately NOT exported: descriptions, contact emails, student names,
project descriptions, image URLs from the upstream dataset.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse

from common import CURATED, EXPORT, GSOC_YEARS, RAW_GSOC, now_iso, read_json, slugify, write_json

GH_RE = re.compile(r"^https?://(www\.)?github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})(/|$)", re.I)
GH_IO_RE = re.compile(r"^https?://([A-Za-z0-9][A-Za-z0-9-]{0,38})\.github\.io(/|$)", re.I)
# Logins that are not organisations we want to map to.
GH_IGNORE = {"orgs", "topics", "features", "about", "apps", "sponsors", "marketplace", "settings", "login", "search"}


def load_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    p = CURATED / "org_aliases.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["alias"].strip().lower()] = row["canonical"].strip()
    return out


def load_manual_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    p = CURATED / "org_github_map.csv"
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["slug"].strip()] = {
                    "github_orgs": [g.strip() for g in row["github_orgs"].split("|") if g.strip()],
                    "source": row.get("source", "manual").strip() or "manual",
                    "note": row.get("note", "").strip(),
                }
    return out


def gh_login_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = GH_RE.match(url.strip())
    if m:
        login = m.group(2)
        return None if login.lower() in GH_IGNORE else login
    m = GH_IO_RE.match(url.strip())
    if m:
        return m.group(1)
    return None


def norm_host(url: str) -> str:
    try:
        u = urlparse(url.strip())
    except Exception:
        return ""
    host = (u.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (u.path or "/").rstrip("/") or "/"
    return f"{host}{path}"


class DSU:
    def __init__(self):
        self.p: dict[str, str] = {}

    def add(self, k):
        self.p.setdefault(k, k)

    def find(self, k):
        while self.p[k] != k:
            self.p[k] = self.p[self.p[k]]
            k = self.p[k]
        return k

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def main() -> int:
    aliases = load_aliases()
    manual = load_manual_map()

    records: list[dict] = []  # one per (org, year)
    for year in GSOC_YEARS:
        path = RAW_GSOC / f"{year}.json"
        if not path.exists():
            print(f"missing {path}; run pipeline/fetch_gsoc_dataset.py", file=sys.stderr)
            return 1
        data = read_json(path)
        for o in data["organizations"]:
            raw_name = (o.get("name") or "").strip()
            name = aliases.get(raw_name.lower(), raw_name)
            records.append(
                {
                    "year": year,
                    "name": name,
                    "raw_name": raw_name,
                    "url": (o.get("url") or "").strip(),
                    "category": (o.get("category") or "").strip(),
                    "projects_url": o.get("projects_url") or "",
                    "ideas_url": o.get("ideas_url") or "",
                    "guide_url": o.get("guide_url") or "",
                    "chat_url": o.get("irc_channel") or "",
                    "mailing_list": o.get("mailing_list") or "",
                    "blog_url": o.get("blog_url") or "",
                    "topics": [t for t in (o.get("topics") or []) if t],
                    "technologies": [t for t in (o.get("technologies") or []) if t],
                    "num_projects": int(o.get("num_projects") or len(o.get("projects") or [])),
                }
            )

    # Merge by case-insensitive name OR same normalised homepage URL.
    dsu = DSU()
    by_name: dict[str, str] = {}
    by_url: dict[str, str] = {}
    for i, r in enumerate(records):
        k = str(i)
        dsu.add(k)
        n = r["name"].lower()
        if n in by_name:
            dsu.union(k, by_name[n])
        else:
            by_name[n] = k
        u = norm_host(r["url"]) if r["url"] else ""
        if u and u not in ("", "/"):
            if u in by_url:
                dsu.union(k, by_url[u])
            else:
                by_url[u] = k

    groups: dict[str, list[dict]] = defaultdict(list)
    for i, r in enumerate(records):
        groups[dsu.find(str(i))].append(r)

    orgs: list[dict] = []
    used_slugs: set[str] = set()
    review_rows: list[dict] = []
    for members in groups.values():
        members.sort(key=lambda r: r["year"])
        latest = members[-1]
        name = latest["name"]
        slug = slugify(name)
        base = slug
        n = 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add(slug)

        years = {}
        all_names = sorted({m["name"] for m in members} | {m["raw_name"] for m in members})
        topics: list[str] = []
        techs: list[str] = []
        for m in members:
            years[str(m["year"])] = {"num_projects": m["num_projects"], "projects_url": m["projects_url"]}
            if m["year"] >= latest["year"] - 2:  # recent three participations only
                for t in m["topics"]:
                    if t not in topics:
                        topics.append(t)
                for t in m["technologies"]:
                    if t not in techs:
                        techs.append(t)

        def latest_nonempty(field):
            for m in reversed(members):
                if m[field]:
                    return m[field]
            return ""

        # GitHub org heuristics: homepage, ideas URL, guide URL, blog URL.
        candidates: list[tuple[str, str]] = []
        for field in ("url", "ideas_url", "guide_url", "blog_url"):
            for m in reversed(members):
                login = gh_login_from_url(m[field])
                if login and login.lower() not in {c[0].lower() for c in candidates}:
                    candidates.append((login, field))
        if slug in manual:
            github_orgs = manual[slug]["github_orgs"]
            gh_source = manual[slug]["source"]
        elif candidates and candidates[0][1] == "url":
            github_orgs = [candidates[0][0]]
            gh_source = "derived:homepage"
        elif candidates:
            github_orgs = [candidates[0][0]]
            gh_source = f"derived:{candidates[0][1]}"
        else:
            github_orgs = []
            gh_source = None
        review_rows.append(
            {
                "slug": slug,
                "name": name,
                "homepage": latest_nonempty("url"),
                "candidates": "|".join(f"{c[0]}({c[1]})" for c in candidates),
                "chosen": "|".join(github_orgs),
                "source": gh_source or "",
                "years": len(years),
            }
        )

        orgs.append(
            {
                "slug": slug,
                "name": name,
                "aliases": [a for a in all_names if a != name],
                "category": latest_nonempty("category"),
                "url": latest_nonempty("url"),
                "ideas_url": latest_nonempty("ideas_url"),
                "guide_url": latest_nonempty("guide_url"),
                "chat_url": latest_nonempty("chat_url"),
                "mailing_list": latest_nonempty("mailing_list"),
                "topics": topics,
                "technologies": techs,
                "years": years,
                "first_year": members[0]["year"],
                "last_year": latest["year"],
                "years_count": len(years),
                "total_projects": sum(m["num_projects"] for m in members),
                "github_orgs": github_orgs,
                "github_source": gh_source,
                "source": "nishantwrp/gsoc-organizations (derived fields only)",
                "fetched_at": now_iso(),
                "last_verified": None,
            }
        )

    orgs.sort(key=lambda o: o["name"].lower())
    write_json(EXPORT / "orgs.json", orgs)

    by_year: dict[str, list[str]] = {str(y): [] for y in GSOC_YEARS}
    for o in orgs:
        for y in o["years"]:
            by_year[y].append(o["slug"])
    write_json(EXPORT / "org_years.json", {"years": by_year, "generated_at": now_iso()})

    EXPORT.mkdir(parents=True, exist_ok=True)
    with open(EXPORT / "org_github_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(review_rows[0].keys()))
        w.writeheader()
        for r in sorted(review_rows, key=lambda r: (-r["years"], r["slug"])):
            w.writerow(r)

    mapped = sum(1 for o in orgs if o["github_orgs"])
    print(f"orgs: {len(orgs)}  org-years: {len(records)}  with github org: {mapped}  "
          f"(manual {sum(1 for o in orgs if o['github_source'] and o['github_source'].startswith('manual'))})")
    for y in GSOC_YEARS:
        print(f"  {y}: {len(by_year[str(y)])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
