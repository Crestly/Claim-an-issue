"""Download the community GSoC organisation dataset (nishantwrp/gsoc-organizations).

External call: raw.githubusercontent.com, 11 GET requests (~17 MB total),
no rate limit issues at this volume. The files are NOT committed (licence not
stated upstream); they are fetched at build time and only derived fields are
exported. See docs/SOURCES.md.
"""
from __future__ import annotations

import sys
import urllib.request

from common import GSOC_YEARS, RAW_GSOC

BASE = "https://raw.githubusercontent.com/nishantwrp/gsoc-organizations/master/api/data/{year}.json"


def main(force: bool = False) -> int:
    RAW_GSOC.mkdir(parents=True, exist_ok=True)
    for year in GSOC_YEARS:
        dest = RAW_GSOC / f"{year}.json"
        if dest.exists() and not force:
            continue
        url = BASE.format(year=year)
        print(f"fetch {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "claimanissue-pipeline (+https://github.com/Crestly/Claim-an-issue)"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
