# Show HN draft

Rules to follow (verify on news.ycombinator.com/showhn.html the day you post): the thing must be usable without signup (it is); do not ask for upvotes anywhere; post one maker comment and then answer questions. Post mid-morning US Eastern on a weekday. Numbers in brackets come from `/api/v1/meta.json`.

## Title (â‰¤ 80 chars; pick one)

- Show HN: Good-first-issue finder that says whether someone already claimed it
- Show HN: Open-source issues with an evidence-backed "is anyone on this?" verdict
- Show HN: [SITE] â€“ GSoC orgs mapped to live GitHub issues, with claim detection

## URL

[URL]

## Maker comment (post immediately after submitting)

I kept opening "good first issue" threads and finding three old "can I take this?" comments with no way to tell if any led to a PR. So this fetches assignees, linked/cross-referenced PRs and the last ten comments per issue and applies four published rules: claimed, stale claim (14 days idle, shown as "may be free again", never as free), open, restricted (repo forbids AI on GFIs or limits first-time PRs). Evidence is shown next to each verdict and links to GitHub, which is the source of truth.

Accuracy: [either "not yet measured; verdicts are labelled unverified until a 200-issue blind eval is done, protocol in the repo" or "blind sample of n=[n]: precision for taken [x]% (CI aâ€“b), for free [y]% (CI câ€“d); confusion matrix on /methodology"]. Known misses: claims in chat, non-English claims, claims deeper than ten comments.

The other half is for Google Summer of Code: every mentoring org 2016â€“2026 ([518] after merging renames) with its live newcomer issues, and one ICS calendar for GSoC/Outreachy/LFX/Summer of Bitcoin/MLH/Season of KDE with a last-verified date on each entry. (Not affiliated with Google.)

Deliberate limits: no bot, it never comments or assigns; no comment text, authors or emails are stored or served; maintainers opt out with one issue or a `.claimable.yml`, permanent within 72 h. Astro static on Vercel, Python stdlib pipeline on Actions cron, SQLite with daily snapshots in a git branch, JSON API without a key (CC BY 4.0). Built with heavy use of an AI coding assistant under my review. Source: [REPO].

Things I'd like critique on: the stale-claim heuristic, and whether the repo health numbers (first-time merge rate, time to first maintainer response, estimated bot PR share) are fair to maintainers.

## Answers to prepare

- "How is this different from goodfirstissue.org?" They show the label; this tries to answer whether anyone is already on it, and keeps history. They have far more repos. Link to them.
- "Doesn't this encourage AI-generated drive-by PRs?" Restricted state hides GFIs from repos that forbid it; the site shows each repo's AI policy; and it filters nothing by ease, only by whether a human is likely needed.
- "Will you email contributors / build a job board?" No; GitHub AUP forbids it and so does the site's policy.
- "Can maintainers remove their repo?" Yes, see /opt-out.
