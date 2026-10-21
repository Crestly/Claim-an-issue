# NEEDS_OWNER.md

Everything the build cannot do without you. Nothing below blocks local
development; the site builds from fixtures and the community dataset today.
Items are ordered by when you need them.

## Before first push (15 minutes)

1. **Name decision.** `Claimable` conflicts with a live UK trademark and a
   pending US application, both for software (see `PLAN.md` section 1). Pick a
   name, do your own search at
   https://tmsearch.uspto.gov, https://www.gov.uk/search-for-trademark and
   https://ised-isde.canada.ca/cipo (you are in Canada), then set `SITE_NAME`
   and `SITE_URL` in `site/src/config.ts`. Recommended: **FirstPatch**
   (`firstpatch.dev`, about US$12/year at most registrars; RDAP showed it
   unregistered on 2026-10-21, re-check).
   Never put "GSoC" or "Summer of Code" in the name, domain or any handle.
2. **Create the public GitHub repo** and push `main` and the empty `data`
   branch:
   ```
   git remote add origin git@github.com:<you>/<repo>.git
   git push -u origin main
   git checkout --orphan data && git rm -rf . && git commit --allow-empty -m "data branch" && git push -u origin data && git checkout main
   ```
3. **Set `REPO_SLUG`** in `site/src/config.ts` to `<you>/<repo>` (used by the
   "report wrong verdict" and opt-out links). The same placeholder `OWNER/claimable`
   also appears in `pipeline/github_api.py` (User-Agent string GitHub asks for) and
   `.github/ISSUE_TEMPLATE/config.yml`; `rg OWNER/claimable` finds all three.

## Before the first pipeline run (10 minutes)

4. **Fine-grained personal access token** (not `GITHUB_TOKEN`):
   Settings -> Developer settings -> Fine-grained tokens. Resource owner: you.
   Repository access: *Public repositories (read-only)*. No extra permissions
   needed for reading public data. For the keepalive re-enable step you also
   need a *second* token with `Actions: read and write` on this repo only.
   Store them as Actions secrets `CLAIMABLE_PAT` and `ACTIONS_ADMIN_PAT`.
   Never share tokens or rotate them to exceed limits.
5. **Enable Actions** on the repo and run `refresh.yml` manually once
   (workflow_dispatch). The first run executes `pipeline/verify_qualifiers.py`
   and writes `docs/VERIFIED_QUALIFIERS.md`; read it.

## Before the site goes public (1–2 hours)

6. **Cloudflare account** (free). Pages -> Create project -> connect the repo.
   Build command `cd site && npm ci && npm run build`, output `site/dist`,
   Node 22. You get `<project>.pages.dev` immediately; add the custom domain
   later. Enable WHOIS privacy at the registrar.
7. **Monitored contact address** for opt-outs. A free alias on your existing
   mail (for example a Cloudflare Email Routing address on the domain). Put it
   in `site/src/config.ts` `CONTACT_EMAIL`. You commit to actioning opt-outs
   within 72 hours.
8. **Mailing address** is NOT needed at launch (no email list). When you add
   email later, CASL requires a valid mailing address in every message. Use a
   PO box or a business address, never your home.
9. **Blind evaluation (about 3–4 hours).** Run
   `python pipeline/run.py sample-eval` after a pipeline run; it writes
   `eval/sample_YYYY-MM-DD.csv` with 200 issue URLs and NO verdicts. Label each
   row by opening the GitHub link (instructions in `eval/README.md`). Then run
   `python eval/score.py`. Until this is done, every verdict on the site is
   shown as "unverified". Repeat monthly.
10. **Google Search Console**: add the domain, submit `/sitemap-index.xml`.

## Ask-before-doing items (I did not do these for you)

11. **Open an issue on `nishantwrp/gsoc-organizations`** asking whether the
    JSON data may be redistributed and under what licence. Draft:
    > Hi, thanks for maintaining this. I'm building a free, non-commercial
    > site that links GSoC organisations to their live GitHub issues. I'd like
    > to use your per-year JSON (names, URLs, categories, technologies, ideas
    > and guide URLs) as a seed. I will not copy descriptions, student names or
    > contact emails, and I'll credit this repo on every org page. Is that OK,
    > and could you state a licence for the data files? Happy to contribute
    > alias fixes back.
12. **Post launch drafts** in `launch/` yourself after editing. Read
    r/learnprogramming and r/opensource rules in a browser first (I could not
    fetch Reddit server-side).
13. **Email gsoc-support@google.com** only if you are unsure about the name.
    The brand guidelines allow referring to GSoC on a page about GSoC, and
    require the footer sentence we already use.

## Nice to have

14. A 1200x630 PNG logo at `site/public/og-default.png` (a generated
    placeholder is included).
15. A PO box when email starts.
