"""Snapshot persistence. The SQLite file is rebuilt each run, so history lives in
the `data` branch of the repo as dated, gzip-compressed CSV files:

  snapshots/issue_snapshots/YYYY-MM-DD.csv.gz
  snapshots/repo_health_snapshots/YYYY-MM-DD.csv.gz
  snapshots/claim_events/YYYY-MM-DD.csv.gz
  state/issues.csv.gz   (latest `issues` table; lets the next run know what it tracked)
  state/repos.csv.gz

`dump()` writes today's files into a working directory (the checked-out data
branch). `restore()` loads everything back into a fresh database. The GitHub
workflow commits the directory to the `data` branch. Size: roughly 100-150
bytes per issue-day compressed -> ~1 MB/day at 10k issues, ~400 MB/year; we
move months older than 12 to Release assets before the 1 GB soft limit.
"""
from __future__ import annotations

import csv
import gzip
import io
import sqlite3
from pathlib import Path

from common import today

SNAPSHOT_TABLES = ["issue_snapshots", "repo_health_snapshots", "claim_events"]
STATE_TABLES = ["repos", "issues", "optouts", "eval_labels", "runs"]


def _write_csv_gz(path: Path, rows: list[sqlite3.Row]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=rows[0].keys())
    w.writeheader()
    for r in rows:
        w.writerow(dict(r))
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    return len(rows)


def dump(conn: sqlite3.Connection, workdir: Path, day: str | None = None) -> dict[str, int]:
    day = day or today()
    out = {}
    for t in SNAPSHOT_TABLES:
        col = "day" if t != "claim_events" else "substr(at,1,10)"
        rows = conn.execute(f"SELECT * FROM {t} WHERE {col} = ?", (day,)).fetchall()
        out[t] = _write_csv_gz(workdir / "snapshots" / t / f"{day}.csv.gz", rows)
    for t in STATE_TABLES:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        out[t] = _write_csv_gz(workdir / "state" / f"{t}.csv.gz", rows)
    return out


def _load_csv_gz(conn: sqlite3.Connection, table: str, path: Path) -> int:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return 0
    cols = reader.fieldnames or []
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    cols = [c for c in cols if c in existing]
    placeholders = ",".join("?" for _ in cols)
    conn.executemany(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                     [[(None if r[c] == "" else r[c]) for c in cols] for r in rows])
    return len(rows)


def restore(conn: sqlite3.Connection, workdir: Path, *, days: int | None = None) -> dict[str, int]:
    """Load state tables and all (or the last N days of) snapshots into conn."""
    out: dict[str, int] = {}
    conn.execute("PRAGMA foreign_keys=OFF")
    for t in STATE_TABLES:
        p = workdir / "state" / f"{t}.csv.gz"
        if p.exists():
            out[t] = _load_csv_gz(conn, t, p)
    for t in SNAPSHOT_TABLES:
        files = sorted((workdir / "snapshots" / t).glob("*.csv.gz"))
        if days:
            files = files[-days:]
        out[t] = sum(_load_csv_gz(conn, t, p) for p in files)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    return out
