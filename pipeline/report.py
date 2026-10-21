"""Weekly health report (Markdown to stdout). Reads data/export/meta.json,
data/last_run.json and, if present, the restored data branch for snapshot counts.

    python pipeline/report.py --data-dir .data-branch
"""
from __future__ import annotations

import argparse
import gzip
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, EXPORT, read_json  # noqa: E402


def count_rows(path: Path) -> int:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)
    except OSError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    meta = read_json(EXPORT / "meta.json") if (EXPORT / "meta.json").exists() else {}
    last = read_json(DATA / "last_run.json") if (DATA / "last_run.json").exists() else {}
    gen = meta.get("generated_at")
    age_h = (now - datetime.fromisoformat(gen.replace("Z", "+00:00"))).total_seconds() / 3600 if gen else None
    lines = [f"## Weekly health report — {now.date().isoformat()}", ""]
    lines.append(f"* Last export: {gen or 'never'}" + (f" ({age_h:.0f} h ago)" if age_h is not None else "") + (" [STALE]" if age_h and age_h > 36 else ""))
    c = meta.get("counts") or {}
    lines.append(f"* Issues tracked: {c.get('issues', 0)} (open {c.get('open', 0)}, claimed {c.get('claimed', 0)}, stale {c.get('stale_claim', 0)}, restricted {c.get('restricted', 0)}); repos {c.get('repos', 0)}; GSoC orgs with live issues {c.get('orgs_with_issues', 0)}")
    q = (last.get("quota") or {})
    r = (last.get("run") or {})
    lines.append(f"* Last run `{r.get('run_id', '?')}`: REST {q.get('rest_used', '?')} used, GraphQL {q.get('graphql_used', '?')} points, search {q.get('search_used', '?')} calls, errors {q.get('errors', '?')}; repos refreshed {r.get('repos_refreshed', '?')}, issues seen {r.get('issues_seen', '?')}")
    ev = meta.get("eval") or {}
    if ev.get("done"):
        lines.append(f"* Classifier eval ({ev.get('sample_date')}, n={ev.get('n')}): precision taken {ev.get('precision_claimed'):.3f}, precision free {ev.get('precision_open'):.3f}; bar {'MET' if ev.get('bar_met') else 'NOT MET'}")
    else:
        lines.append("* Classifier eval: **not done** — verdicts are shown as unverified. See eval/README.md.")
    if args.data_dir:
        d = Path(args.data_dir) / "snapshots"
        days = sorted(p.stem.replace(".csv", "") for p in (d / "issue_snapshots").glob("*.csv.gz")) if d.exists() else []
        week = [x for x in days if x >= (now - timedelta(days=7)).date().isoformat()]
        lines.append(f"* Snapshot days total: {len(days)}; last 7 days: {len(week)}/7 {'ok' if len(week) >= 6 else '[MISSED DAYS]'}")
        if days:
            total_rows = sum(count_rows(d / "issue_snapshots" / f"{x}.csv.gz") for x in week)
            lines.append(f"* Issue-snapshot rows this week: {total_rows}")
        ce = d / "claim_events"
        if ce.exists():
            ev_rows = sum(count_rows(p) for p in ce.glob("*.csv.gz") if p.stem.replace(".csv", "") >= (now - timedelta(days=7)).date().isoformat())
            lines.append(f"* Claim events this week: {ev_rows}")
    lines += ["", "### Checklist", "- [ ] Any opt-out requests older than 72 h? (issues labelled `opt-out`)", "- [ ] Any `wrong-verdict` reports to triage?",
              "- [ ] Official GSoC timeline/blog checked (daily Jan 1 – Apr 30)", "- [ ] Monthly blind eval due?"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
