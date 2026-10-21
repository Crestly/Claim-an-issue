// Single source of truth for naming and owner-specific values.
// Renaming the product = change SITE_NAME and SITE_URL here (see NEEDS_OWNER.md).
// Never put "GSoC" or "Summer of Code" in SITE_NAME, SITE_URL or handles.

export const SITE_NAME = 'Claimable';
export const SITE_TAGLINE = 'Open-source issues that genuinely need a person, with evidence.';
export const SITE_URL = 'https://claimable.pages.dev'; // replace with the real domain
export const REPO_SLUG = 'OWNER/claimable'; // replace: GitHub "owner/repo" of this project
export const CONTACT_EMAIL = 'optout@example.invalid'; // replace: monitored address for opt-outs
export const DATA_VERSION = 'v1';

export const REPO_URL = `https://github.com/${REPO_SLUG}`;
export const OPTOUT_ISSUE_URL = `${REPO_URL}/issues/new?template=opt-out.yml`;
export const REPORT_ISSUE_URL = `${REPO_URL}/issues/new?template=wrong-verdict.yml`;

// Google's exact attribution sentence from the GSoC brand guidelines (verified 2026-10-21).
export const GSOC_NOTICE = `"Summer of Code" is a trademark of Google and ${SITE_NAME} is not affiliated with Google or Google's Summer of Code.`;

// Shown on every verdict.
export const VERDICT_DISCLAIMER = 'Every verdict is an automated estimate. GitHub is the source of truth.';
