# OPERATIONS.md

## Daily (automatic)
* `refresh.yml` runs 3Ã—/day. It restores the last 45 days of snapshots from the
  `data` branch, refreshes, exports JSON, commits exports to `main` (which
  triggers a Vercel deploy), and commits today's snapshot files to
  `data`.
* `data/last_run.json` (and the Actions artifact) holds the run log and quota.

## Weekly (automatic)
* `weekly-report.yml` opens an `ops` issue with snapshot counts, quota, errors
  and the eval status.
* `keepalive-check.yml` re-enables scheduled workflows via the Actions API
  (needs `ACTIONS_ADMIN_PAT`) and opens an issue if no refresh succeeded in 36 h.

## Uptime check (free, external)
Scheduled workflows cannot alert you if Actions itself is disabled. Add one
free monitor (for example UptimeRobot or Cloudflare's health checks on a paid
plan; UptimeRobot Free: 50 monitors, 5-minute interval) on
`https://<site>/api/v1/meta.json` with a keyword check that `generated_at`
contains the current month, or simply HTTP 200 on `/`. Put the monitor's
email on the owner's phone.

## Manual, by the owner
* Opt-outs: issues labelled `opt-out` or emails. Add to
  `data/curated/optouts.json`, commit; applied at the next run (max 72 h, the
  pipeline runs 3Ã—/day). Never reply publicly on the maintainer's repo.
* Wrong-verdict reports: issues labelled `wrong-verdict`. Reproduce, fix rules
  or patterns in `pipeline/classify.py`, add a unit test, note in CHANGELOG.
* Monthly: `python pipeline/run.py sample-eval`, label, `python eval/score.py`,
  commit. See `eval/README.md`.
* Jan 1 â€“ Apr 30: check the official GSoC timeline and blog daily; update
  `data/curated/programs.json` the day dates are published (status `verified`,
  `last_verified` = today).
* Snapshot size: when the `data` branch exceeds ~800 MB, move months older
  than 12 into a GitHub Release asset (`gh release create snapshots-YYYY -F ...`)
  and delete them from the branch (`git rm`, then `git push --force` is NOT
  needed; history remains but a shallow clone stays small).

## Restore from a clean checkout (tested)
```
git clone --branch data --depth 1 https://github.com/<you>/<repo>.git .data-branch
python pipeline/run.py restore-test --data-dir .data-branch
```
`run.py fixture` performs the same dumpâ†’restore round trip on fixtures in CI.

## Rotating the token
Create a new fine-grained PAT, update the `CLAIMABLE_PAT` secret, revoke the
old one. Never run two tokens in parallel to raise limits.

## Incident: Search returns 422
A qualifier was rejected. Run `python pipeline/verify_qualifiers.py` and read
`docs/VERIFIED_QUALIFIERS.md`; adjust `discover.py`.
