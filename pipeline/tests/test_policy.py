import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from policy import detect_ai_policy, detect_first_time_restriction, parse_claimable_yml  # noqa: E402


class PolicyTests(unittest.TestCase):
    def test_unknown(self):
        self.assertEqual(detect_ai_policy({"CONTRIBUTING.md": "Please run the tests before opening a PR."}), ("unknown", None))

    def test_forbids_gfi(self):
        text = "Good first issues are meant for learning. The use of AI tools is not allowed when working on good first issues."
        self.assertEqual(detect_ai_policy({"CONTRIBUTING.md": text})[0], "forbids-gfi")

    def test_forbids(self):
        text = "We do not accept AI-generated pull requests. Submissions produced by ChatGPT or Copilot will be closed."
        self.assertEqual(detect_ai_policy({"CONTRIBUTING.md": text})[0], "forbids")

    def test_disclosure(self):
        text = "If you used an AI assistant to write code, you must disclose it in the PR description (Assisted-by: trailer)."
        self.assertEqual(detect_ai_policy({"AI_POLICY.md": text})[0], "disclosure")

    def test_allows(self):
        text = "You are free to use AI tools such as Copilot; you remain responsible for the result."
        self.assertEqual(detect_ai_policy({"AGENTS.md": text})[0], "allows")

    def test_override(self):
        self.assertEqual(detect_ai_policy({"CONTRIBUTING.md": "AI is banned"}, override="allows"), ("allows", ".claimable.yml"))

    def test_first_time_restriction(self):
        text = "First-time contributors must be assigned to an issue before opening a pull request."
        self.assertTrue(detect_first_time_restriction({"CONTRIBUTING.md": text})[0])
        self.assertFalse(detect_first_time_restriction({"CONTRIBUTING.md": "Welcome, first-time contributors! Pick any issue."})[0])

    def test_yaml_subset(self):
        y = 'index: false\nclaim_required: true\nclaim_commands: ["/assign", "/take"]\nlabels:\n  - "E-easy"\n  - starter\nmax_open_prs_per_newcomer: 2\nai_policy: disclosure # comment\n'
        d = parse_claimable_yml(y)
        self.assertEqual(d["index"], False)
        self.assertEqual(d["claim_commands"], ["/assign", "/take"])
        self.assertEqual(d["labels"], ["E-easy", "starter"])
        self.assertEqual(d["max_open_prs_per_newcomer"], 2)
        self.assertEqual(d["ai_policy"], "disclosure")


if __name__ == "__main__":
    unittest.main()
