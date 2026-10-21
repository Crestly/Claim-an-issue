# SOURCES.md — data sources, licences, credits

| Source | What we use | Licence | Notes |
|---|---|---|---|
| GitHub REST + GraphQL API | issue/repo/PR metadata | GitHub Terms of Service; Acceptable Use Policies | No comment text, comment authors or emails stored. Never used for spam, recruiting or contact. |
| [nishantwrp/gsoc-organizations](https://github.com/nishantwrp/gsoc-organizations) | GSoC org names, years, categories, technologies, topics, official URLs (2016–2026) | Code GPL-3.0; **data licence not stated** | Permission requested (see NEEDS_OWNER.md item 11). Descriptions, images, contact emails and student names are NOT used. Credited on every org page and in the footer. Raw files are fetched at build time and not committed. |
| Google Open Source — GSoC timeline, FAQ, brand guidelines, stats | 2026 dates, eligibility, footer wording, official org counts 2005–2024 | © Google; facts | Read 2026-10-21. "Summer of Code" and "GSoC" are Google trademarks. |
| outreachy.org | December 2026 round dates and open communities | © Software Freedom Conservancy; facts | Read 2026-10-21. |
| [melissawm/open-source-ai-contribution-policies](https://github.com/melissawm/open-source-ai-contribution-policies) | examples of AI policies cited on /about and /start-now | see repo | Our per-repo detection is our own regex over each repo's files. |
| [hao-li/AIDev](https://github.com/hao-li/AIDev) | seed ideas for AI-agent login patterns | see repo | Only pattern names (copilot, claude, devin, …) are used; no data copied. |
| Steinmacher et al., CSCW 2015, doi:10.1145/2675133.2675215 | newcomer barriers (cited) | academic | |
| goodfirstissue.org /about | competitor facts (cited) | © its authors | Read 2026-10-21. |

Not used: summerofcode.withgoogle.com scraping (robots.txt returns 404, terms
not reviewed in a browser; we link out instead), ecosyste.ms (CC BY-SA
share-alike; not a dependency), ketankauntia/gsoc-orgs (non-commercial
licence; not used).

Our outputs: code MIT (`LICENSE`), data CC BY 4.0 (`data/LICENSE-DATA.md`).
