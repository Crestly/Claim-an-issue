import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { issues, orgs, meta } from '../../lib/data';
import { SITE_NAME, SITE_URL } from '../../config';

// Feeds: all, per language (python, rust, ...), per GSoC org (org-<slug>). Only state=open issues,
// newest first, 50 items. Items link to GitHub; the description carries the evidence summary only.
function langKey(l: string | null) { return (l ?? 'other').toLowerCase().replace(/[^a-z0-9+#.-]+/g, '-'); }

export function getStaticPaths() {
  const feeds = new Set<string>(['all']);
  for (const i of issues) feeds.add(langKey(i.language));
  for (const o of orgs) if (issues.some((i) => i.gsoc_org_slug === o.slug)) feeds.add(`org-${o.slug}`);
  return [...feeds].map((feed) => ({ params: { feed } }));
}

export async function GET(context: APIContext) {
  const feed = context.params.feed!;
  let items = issues.filter((i) => i.state === 'open');
  let title = `${SITE_NAME}: new open issues`;
  if (feed.startsWith('org-')) { const slug = feed.slice(4); items = items.filter((i) => i.gsoc_org_slug === slug); title = `${SITE_NAME}: open issues at ${orgs.find((o) => o.slug === slug)?.name ?? slug}`; }
  else if (feed !== 'all') { items = items.filter((i) => langKey(i.language) === feed); title = `${SITE_NAME}: open ${feed} issues`; }
  items = items.sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 50);
  return rss({
    title,
    description: `Newcomer-labelled issues judged open (no assignee, no linked PR, no unanswered claim) as of ${meta.generated_at}. Automated estimate; GitHub is the source of truth.`,
    site: SITE_URL,
    items: items.map((i) => ({
      title: `${i.repo}#${i.number}: ${i.title}`,
      link: i.url,
      pubDate: new Date(i.created_at),
      description: `${i.language ?? ''} · ${i.labels.join(', ')} · ${i.comments} comments · verdict: open${i.verdict_verified ? '' : ' (unverified)'}. Details: ${SITE_URL}/issues/?issue=${i.id}`,
      categories: [i.language ?? 'other', ...i.labels.slice(0, 3)],
    })),
    customData: `<language>en</language><ttl>480</ttl>`,
  });
}
