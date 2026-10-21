---
title: I built a "good first issue" finder that tells you whether someone already claimed it
published: false
tags: showdev, opensource, gsoc, github
---

<!-- DEV.to draft. Replace [SITE], [URL], and every bracketed number from /api/v1/meta.json on the day. Keep the AI disclosure. -->

**TL;DR:** [SITE] ([URL]) lists open-source issues labelled for newcomers and, for each one, says whether it is actually **open**, **claimed**, a **stale claim**, or **restricted**, with the evidence (assignee, linked PR, a claim comment with no maintainer reply, the repo's AI policy). It is free, static, has no login, and every GSoC mentoring org since 2016 is linked to its live issues. The rules and the measured error rate are public.

## The problem I kept hitting

Every good-first-issue site shows the label. None of them answers the question you actually have: *is somebody already working on this?* You open the issue, scroll past three "can I take this?" comments from months ago, can't tell whether any of them went anywhere, and give up or duplicate someone's work.

The second problem is seasonal. If you are preparing for Google Summer of Code, you want to contribute to a *mentoring organization* early, and "which orgs, which repos, which issues are open right now" is spread across a dozen pages.

## What it does

For each issue in a few thousand tracked repositories ([N repos], [M issues] right now), the pipeline fetches assignees, linked and cross-referenced pull requests, and the last ten comments (read in memory, never stored), then applies four published rules:

- **Claimed**: an assignee, an open linked PR, or a claim comment with no maintainer rebuttal.
- **Stale claim**: a claim or assignee with no PR and no activity for 14 days. Shown as "may be free again", never as free.
- **Open**: none of the above.
- **Restricted**: the repo forbids AI use on good first issues or limits first-time PRs. We do not promote those as beginner targets.

Each verdict comes with its evidence and a link to GitHub, which is the source of truth. Repos get health numbers (first-time-contributor merge rate, median time to first maintainer response, setup friction, an *estimated* bot/agent PR share), shown only when the sample is at least 10.

## How accurate is it?

[Pick one, honestly:]

- *Before the evaluation:* I have not measured it yet. Every verdict is labelled "unverified" on the site until a 200-issue blind evaluation is done. The protocol and the bar (claimed-vs-open precision ≥ 90 %) are in the repo.
- *After the evaluation:* On a blind sample of [n] issues, precision for "taken" was [x] % (95 % CI [a–b]) and for "free" was [y] % ([c–d]). Full confusion matrix on the methodology page.

Known failure modes: claims made in chat, non-English claims, claims buried deeper than the last ten comments.

## The GSoC part

All [518] organizations that mentored between 2016 and 2026, merged across renames, each with its official links, years and project counts, and the live newcomer issues from its GitHub organizations. Plus one calendar (with an ICS feed) for GSoC, Outreachy, LFX Mentorship, Summer of Bitcoin, MLH Fellowship and Season of KDE, with a "last verified" date on every entry, and a "start now for GSoC 2027" page that is explicit about which dates are announced and which are only the expected pattern.

"Summer of Code" is a trademark of Google; [SITE] is not affiliated with Google.

## What it will not do

No bot. It never comments on, assigns or pings issues. It never stores comment text, authors or emails. No rankings of people. Maintainers can opt out a repo or a whole org with one issue, a `.claimable.yml`, or the `no-claimable` topic, applied within 72 hours and permanent.

## Stack, for the curious

Astro static site on Cloudflare Pages; a Python standard-library pipeline on GitHub Actions cron (three runs a day, a documented API budget); SQLite rebuilt each run with daily snapshots in a `data` branch; JSON API under `/api/v1/` with no key, CC BY 4.0. Source: [REPO].

**Disclosure:** I built this with an AI coding assistant doing most of the typing, under my direction and review. The classifier rules, the data-handling limits and the "do not claim what you have not measured" stance are deliberate choices, and the mistakes are mine.

If you maintain a project and the verdicts on your issues are wrong, please tell me via the issue template; wrong-verdict reports feed the published error rate. Also happy to hear what goodfirstissue.org, up-for-grabs or firstissue.dev already do better; I use them too.
