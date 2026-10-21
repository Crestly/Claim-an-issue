import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from classify import classify, match_claim, RULES  # noqa: E402

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def base(**kw):
    d = {"has_assignee": False, "assignee_count": 0, "linked_prs": [], "crossref_prs": [], "comments": [],
         "created_at": ago(30), "updated_at": ago(2), "labels": ["good first issue"], "repo": {"ai_policy": "unknown"}}
    d.update(kw)
    return d


def comment(body, days, assoc="NONE", author="u1", bot=False):
    return {"author_key": author, "author_association": assoc, "is_bot": bot, "created_at": ago(days), "body": body, "url": "https://github.com/o/r/issues/1#issuecomment-1"}


class ClassifyTests(unittest.TestCase):
    def test_open(self):
        self.assertEqual(classify(base(), NOW)["claim_state"], "open")

    def test_assignee_recent_is_claimed(self):
        r = classify(base(has_assignee=True, assignee_count=1), NOW)
        self.assertEqual(r["claim_state"], "claimed")
        self.assertEqual(r["evidence"][0]["kind"], "assignee")

    def test_assignee_idle_is_stale(self):
        r = classify(base(has_assignee=True, assignee_count=1, updated_at=ago(20)), NOW)
        self.assertEqual(r["claim_state"], "stale_claim")

    def test_open_linked_pr_is_claimed_even_if_idle(self):
        r = classify(base(updated_at=ago(40), linked_prs=[{"state": "OPEN", "url": "u", "created_at": ago(35)}]), NOW)
        self.assertEqual(r["claim_state"], "claimed")

    def test_crossref_open_pr_is_claimed(self):
        r = classify(base(crossref_prs=[{"state": "OPEN", "url": "u", "created_at": ago(1)}]), NOW)
        self.assertEqual(r["claim_state"], "claimed")

    def test_closed_pr_only_does_not_claim(self):
        r = classify(base(linked_prs=[{"state": "CLOSED", "url": "u", "created_at": ago(10)}]), NOW)
        self.assertEqual(r["claim_state"], "open")

    def test_claim_comment_claims(self):
        r = classify(base(comments=[comment("Can I work on this?", 3)]), NOW)
        self.assertEqual(r["claim_state"], "claimed")
        self.assertEqual(r["claim_pattern_id"], "phrase_work_on")

    def test_claim_comment_then_idle_is_stale(self):
        r = classify(base(updated_at=ago(20), comments=[comment("I'll take this", 20)]), NOW)
        self.assertEqual(r["claim_state"], "stale_claim")

    def test_maintainer_rebuttal_reopens(self):
        r = classify(base(comments=[comment("I'd like to work on this", 5), comment("This is already assigned to someone else.", 4, "MEMBER", "m1")]), NOW)
        self.assertEqual(r["claim_state"], "open")
        self.assertIsNotNone(r["maintainer_rebuttal_at"])

    def test_maintainer_confirmation_keeps_claim(self):
        r = classify(base(comments=[comment("I'd like to work on this", 5), comment("Sure, go ahead!", 4, "MEMBER", "m1")]), NOW)
        self.assertEqual(r["claim_state"], "claimed")

    def test_release_by_claimant_reopens(self):
        r = classify(base(comments=[comment("/assign", 10), comment("Sorry, I can't work on this anymore", 2, author="u1")]), NOW)
        self.assertEqual(r["claim_state"], "open")

    def test_bot_comments_ignored(self):
        r = classify(base(comments=[comment("I'll take this", 1, bot=True, author="bot[bot]")]), NOW)
        self.assertEqual(r["claim_state"], "open")

    def test_quoted_claim_ignored(self):
        r = classify(base(comments=[comment("> can I work on this?\n\nPlease read the guide first.", 1, "MEMBER", "m1")]), NOW)
        self.assertEqual(r["claim_state"], "open")

    def test_weak_question_by_maintainer_ignored(self):
        r = classify(base(comments=[comment("Is this still available? Bumping for triage.", 1, "MEMBER", "m1")]), NOW)
        self.assertEqual(r["claim_state"], "open")

    def test_restricted_ai_gfi(self):
        r = classify(base(repo={"ai_policy": "forbids-gfi"}), NOW)
        self.assertEqual(r["claim_state"], "restricted")

    def test_restricted_does_not_override_claimed(self):
        r = classify(base(has_assignee=True, repo={"ai_policy": "forbids-gfi"}), NOW)
        self.assertEqual(r["claim_state"], "claimed")

    def test_first_time_pr_restriction(self):
        r = classify(base(repo={"restricted_first_time_prs": True}), NOW)
        self.assertEqual(r["claim_state"], "restricted")

    def test_custom_command(self):
        r = classify(base(repo={"claim_commands": ["!claim"]}, comments=[comment("!claim", 1)]), NOW)
        self.assertEqual(r["claim_state"], "claimed")
        self.assertEqual(r["claim_pattern_id"], "cmd_repo_custom")

    def test_patterns(self):
        yes = [".take-issue", "/assign", "/take", "I would like to work on this issue", "I'll take it", "working on this",
               "Please assign this to me", "Is this still available?", "Can I pick this up?", "I can take this one", "I'd love to give this a try"]
        no = ["Thanks for reporting!", "I can reproduce this on Windows 11.", "This also affects version 2.", "Duplicate of #12", "LGTM"]
        for s in yes:
            self.assertIsNotNone(match_claim(s), s)
        for s in no:
            self.assertIsNone(match_claim(s), s)

    def test_no_text_in_output(self):
        secret = "my-secret-phrase-xyz"
        r = classify(base(comments=[comment(f"I'll take this {secret}", 1)]), NOW)
        self.assertNotIn(secret, str(r))

    def test_rules_mirrored_on_site(self):
        page = Path(__file__).resolve().parents[2] / "site" / "src" / "pages" / "methodology.astro"
        if page.exists():
            text = page.read_text(encoding="utf-8")
            for line in RULES.splitlines():
                head = line.split(":")[0]
                self.assertIn(head, text)


if __name__ == "__main__":
    unittest.main()
