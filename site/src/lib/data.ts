// Build-time data access. Reads generated JSON from ../data/export (pipeline output)
// and ../data/curated (hand-maintained). Missing files degrade to empty data so the
// site always builds; pages then render "no data yet" and are noindexed.
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..', '..', '..');
export const EXPORT_DIR = path.join(ROOT, 'data', 'export');
export const CURATED_DIR = path.join(ROOT, 'data', 'curated');

function readJson<T>(file: string, fallback: T): T {
  if (!existsSync(file)) return fallback;
  return JSON.parse(readFileSync(file, 'utf8')) as T;
}

export interface Org {
  slug: string;
  name: string;
  aliases: string[];
  category: string;
  url: string;
  ideas_url: string;
  guide_url: string;
  chat_url: string;
  mailing_list: string;
  topics: string[];
  technologies: string[];
  years: Record<string, { num_projects: number; projects_url: string }>;
  first_year: number;
  last_year: number;
  years_count: number;
  total_projects: number;
  github_orgs: string[];
  github_source: string | null;
  source: string;
  fetched_at: string;
  last_verified: string | null;
}

export interface ProgramEvent {
  start: string;
  end: string | null;
  title: string;
  kind: 'orgs' | 'contributors' | 'deadline' | 'milestone' | 'phase';
  status: 'verified' | 'from-brief' | 'expected' | 'unverified';
}
export interface Program {
  id: string;
  name: string;
  short: string;
  official_url: string;
  timeline_url: string;
  eligibility_url: string;
  audience: string;
  last_verified: string;
  status: string;
  events: ProgramEvent[];
  open_communities_2026_12?: string[];
}

export interface RepoSummary {
  full_name: string;
  owner: string;
  name: string;
  slug: string;
  description: string | null;
  language: string | null;
  topics: string[];
  stars: number;
  open_claimable: number;
  gsoc_org_slug: string | null;
  health: RepoHealth | null;
  ai_policy: 'allows' | 'disclosure' | 'forbids' | 'forbids-gfi' | 'unknown';
  ai_policy_source: string | null;
  restricted_first_time_prs: boolean;
  last_maintainer_activity: string | null;
  fetched_at: string;
}
export interface RepoHealth {
  first_time_merge_rate: number | null;
  first_time_prs_closed: number;
  median_first_response_hours: number | null;
  first_response_n: number;
  setup_friction: 'low' | 'medium' | 'high' | 'unknown';
  setup_signals: string[];
  bot_pr_share_estimate: number | null;
  bot_pr_n: number;
  negative_metrics_visible: boolean;
}

export interface IssueSummary {
  id: number;
  number: number;
  repo: string;
  title: string;
  url: string;
  state: 'open' | 'claimed' | 'stale_claim' | 'restricted';
  verdict_verified: boolean;
  labels: string[];
  language: string | null;
  created_at: string;
  updated_at: string;
  comments: number;
  age_days: number;
  evidence: Evidence[];
  gsoc_org_slug: string | null;
  fetched_at: string;
}
export interface Evidence {
  kind: 'assignee' | 'linked_pr' | 'cross_ref_pr' | 'claim_comment' | 'maintainer_rebuttal' | 'ai_policy' | 'first_time_restriction' | 'stale';
  detail: string; // derived description, never comment text
  url?: string;
  at?: string;
}

export interface Meta {
  generated_at: string;
  run_id: string | null;
  counts: { repos: number; issues: number; open: number; claimed: number; stale_claim: number; restricted: number; orgs_with_issues: number };
  eval: {
    done: boolean;
    sample_date: string | null;
    n: number;
    precision_claimed: number | null;
    recall_claimed: number | null;
    precision_open: number | null;
    recall_open: number | null;
    ci: Record<string, [number, number]> | null;
    bar_met: boolean;
  };
  quota: { rest_used: number; graphql_used: number; search_used: number } | null;
}

export const orgs: Org[] = readJson(path.join(EXPORT_DIR, 'orgs.json'), [] as Org[]);
export const orgBySlug = new Map(orgs.map((o) => [o.slug, o]));
export const orgYears: Record<string, string[]> = readJson(path.join(EXPORT_DIR, 'org_years.json'), { years: {} as Record<string, string[]> }).years;
export const programs: Program[] = readJson(path.join(CURATED_DIR, 'programs.json'), { programs: [] as Program[] }).programs;
export const repos: RepoSummary[] = readJson(path.join(EXPORT_DIR, 'repos.json'), [] as RepoSummary[]);
export const repoByName = new Map(repos.map((r) => [r.full_name, r]));
export const issues: IssueSummary[] = readJson(path.join(EXPORT_DIR, 'issues.json'), [] as IssueSummary[]);
export const meta: Meta = readJson(path.join(EXPORT_DIR, 'meta.json'), {
  generated_at: '',
  run_id: null,
  counts: { repos: 0, issues: 0, open: 0, claimed: 0, stale_claim: 0, restricted: 0, orgs_with_issues: 0 },
  eval: { done: false, sample_date: null, n: 0, precision_claimed: null, recall_claimed: null, precision_open: null, recall_open: null, ci: null, bar_met: false },
  quota: null,
} as Meta);

export const hasLiveData = issues.length > 0 && !!meta.generated_at;

export function issuesForOrg(slug: string): IssueSummary[] {
  return issues.filter((i) => i.gsoc_org_slug === slug);
}
export function reposForOrg(slug: string): RepoSummary[] {
  return repos.filter((r) => r.gsoc_org_slug === slug);
}
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return iso.slice(0, 10);
}
export function relDays(iso: string): string {
  const d = Math.floor((Date.now() - Date.parse(iso)) / 86400000);
  if (d <= 0) return 'today';
  if (d === 1) return '1 day ago';
  if (d < 30) return `${d} days ago`;
  if (d < 365) return `${Math.floor(d / 30)} mo ago`;
  return `${Math.floor(d / 365)} y ago`;
}
