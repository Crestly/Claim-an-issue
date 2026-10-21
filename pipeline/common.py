"""Shared paths and helpers for the pipeline. Stdlib only."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_GSOC = DATA / "raw" / "gsoc"
CURATED = DATA / "curated"
EXPORT = DATA / "export"
SITE_DATA = ROOT / "site" / "public" / "data"
DOCS = ROOT / "docs"
DB_PATH = DATA / "claimable.sqlite"

GSOC_YEARS = list(range(2016, 2027))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = _slug_re.sub("-", text.lower()).strip("-")
    return text or "org"


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
