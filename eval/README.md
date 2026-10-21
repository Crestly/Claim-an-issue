# Blind evaluation protocol

The classifier's published accuracy comes from this folder and nowhere else.
Until a sample has been labelled and scored, every verdict on the site is
shown as **"unverified"**. This is enforced in `pipeline/export.py`
(`verdict_verified = eval.done and eval.bar_met`).

## Steps (about 3–4 hours for 200 issues)

1. After a pipeline run, draw the sample:
   ```
   python pipeline/run.py sample-eval --n 200
   ```
   This writes `eval/sample_YYYY-MM-DD.csv` with **only** issue URLs, stratified
   by repository size (star terciles) and classifier state so that rare states
   are represented. The classifier's own labels are written to
   `eval/.hidden_YYYY-MM-DD.json`. **Do not open that file**, and do not look
   at the site, until you have finished labelling.
2. For each row, open the GitHub URL and decide, using only what GitHub shows:
   * `claimed` — an assignee, an open PR that references or will close it, or a
     comment where someone says they are working on it and no maintainer said
     otherwise.
   * `stale_claim` — a claim or assignee, but no PR and nothing has happened
     for at least 14 days.
   * `open` — none of the above.
   * `restricted` — the repo's `CONTRIBUTING.md` / policy file forbids AI on
     beginner issues or limits first-time PRs. (Check only if the issue has a
     newcomer label; otherwise label by claim state.)
   * `unsure` — genuinely ambiguous; excluded from scoring and counted.
   Put the label in `human_label`. Notes are optional and never published.
3. Score:
   ```
   python eval/score.py
   ```
   Prints per-class precision/recall with Wilson 95 % intervals and the two
   binary precisions (free vs taken). Writes `eval/results.json`. The next
   pipeline export embeds it in `meta.json`; the site shows it on
   `/methodology` and flips verdicts to verified when the bar is met.
4. Commit `eval/sample_*.csv` (labels) and `eval/results.json`. The
   `.hidden_*.json` files are git-ignored; keep them locally for audit.
5. Repeat monthly on a fresh sample (`sample-eval` uses the date in the file
   name, so old samples are preserved).

## Acceptance bar

Both binary precisions (free = open+restricted; taken = claimed+stale_claim)
at or above **0.90**, with n ≥ 150 labelled rows. If the bar is missed, the
site keeps "unverified" on verdicts and the methodology page shows the actual
numbers and the confusion matrix. Fix the rules, re-run, re-sample; never
re-label the same sample after seeing the classifier output.

## Why blind

If the labeller sees the classifier's verdict first, agreement is inflated.
The sample file therefore contains no verdict, and the strata are not shown
either (they would leak the state).
