"""Detect a repository's AI-contribution policy and first-time-PR restrictions from
text files (AI_POLICY.md, AGENTS.md, CONTRIBUTING.md, .github/CONTRIBUTING.md,
docs/CONTRIBUTING.md). Default is "unknown". Rules are regex heuristics and are
published on /methodology. `.claimable.yml` overrides detection.

Returns ("allows"|"disclosure"|"forbids"|"forbids-gfi"|"unknown", source_or_None).
"""
from __future__ import annotations

import re

POLICY_FILES = ["AI_POLICY.md", "AGENTS.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md", "CONTRIBUTING.rst", "docs/contributing.md"]

AI = r"(?:\bAI\b|\bA\.I\.|LLMs?\b|large[- ]language[- ]models?|ChatGPT|Copilot|Claude|Gemini|generative|machine[- ]generated|AI[- ](?:generated|assisted|written|produced)|vibe[- ]cod)"
NEG = r"(?:do\s+not|don'?t|must\s+not|may\s+not|not\s+(?:be\s+)?(?:accept|allow|permit)|will\s+not\s+(?:be\s+)?(?:accept|merg|review)|prohibit|forbid|ban(?:ned)?|reject|not\s+welcome|disallow|refuse|no\s+(?:AI|LLM))"
GFI = r"(?:good[- ]first[- ]issues?|beginner|starter|first[- ]timers?|newcomer|easy)"

RULES: list[tuple[str, re.Pattern]] = [
    ("forbids-gfi", re.compile(rf"(?is)(?:{GFI}.{{0,250}}{AI}.{{0,120}}{NEG}|{NEG}.{{0,120}}{AI}.{{0,250}}{GFI}|{AI}.{{0,120}}{NEG}.{{0,250}}{GFI})")),
    ("forbids", re.compile(rf"(?is)(?:{NEG}.{{0,100}}{AI}.{{0,120}}(?:contribut|pull\s+requests?|PRs?\b|code|patch|submission)|{AI}.{{0,80}}(?:contribut|pull\s+requests?|PRs?\b|code|patches|submissions?)\b.{{0,100}}{NEG}|(?:contribut|pull\s+requests?|PRs?\b|code|patch|submission)s?\s+(?:that\s+(?:are|were)\s+)?(?:generated|written|produced)\s+(?:by|with|using)\s+{AI}.{{0,120}}(?:not\s+(?:be\s+)?accepted|rejected|closed|prohibited|forbidden|banned))")),
    ("disclosure", re.compile(rf"(?is)(?:{AI}.{{0,160}}(?:disclos|declar|must\s+(?:state|note|say|mention|indicate|label|tag)|transparen|clearly\s+(?:mark|indicat|state)|Assisted-by|AI[- ]disclosure)|(?:disclos|declar|transparen|Assisted-by).{{0,160}}{AI})")),
    ("allows", re.compile(rf"(?is)(?:{AI}.{{0,120}}(?:is|are)\s+(?:allowed|welcome|permitted|fine|acceptable|ok(?:ay)?)|(?:you\s+)?(?:may|can|are\s+free\s+to|are\s+welcome\s+to)\s+use\s+{AI}|{AI}\s+(?:tools?\s+)?(?:may|can)\s+be\s+used)")),
]

FIRST_TIME_RESTRICTION = re.compile(
    r"(?is)(?:first[- ]time\s+contributors?|new\s+contributors?|newcomers?).{0,160}(?:must|should|need\s+to|required\s+to|have\s+to)\s+(?:first\s+)?(?:be\s+assigned|ask|comment|request\s+assignment|get\s+approval|be\s+approved|wait\s+for)"
    r"|(?:do\s+not|don'?t|will\s+not)\s+(?:accept|review|merge)\s+(?:unsolicited\s+)?(?:pull\s+requests?|PRs?)\s+from\s+(?:first[- ]time|new)\s+contributors?"
    r"|(?:pull\s+requests?|PRs?)\s+(?:without|lacking)\s+(?:a\s+)?(?:prior\s+)?(?:assignment|approved\s+issue|linked\s+issue).{0,60}(?:closed|rejected|not\s+accepted)")

NON_POLICY_FALSE_POSITIVES = re.compile(r"(?i)\b(?:AI\s+(?:model|feature|module|package|library|SDK|API)|openai\.com|AI-powered|/ai/)")


def detect_ai_policy(files: dict[str, str | None], override: str | None = None) -> tuple[str, str | None]:
    """files: path -> text (None if missing). override: value from .claimable.yml."""
    if override in ("allows", "disclosure", "forbids", "forbids-gfi"):
        return override, ".claimable.yml"
    best: tuple[int, str, str] | None = None
    order = {"forbids-gfi": 0, "forbids": 1, "disclosure": 2, "allows": 3}
    for path in POLICY_FILES:
        text = files.get(path)
        if not text:
            continue
        # Dedicated policy files are strong signals even for short text.
        for rule_id, rx in RULES:
            if rx.search(text):
                cand = (order[rule_id], rule_id, f"{path}#{rule_id}")
                if best is None or cand < best:
                    best = cand
                break  # first (strongest) matching rule per file
    if best:
        return best[1], best[2]
    return "unknown", None


def detect_first_time_restriction(files: dict[str, str | None]) -> tuple[bool, str | None]:
    for path, text in files.items():
        if text and FIRST_TIME_RESTRICTION.search(text):
            return True, path
    return False, None


def parse_claimable_yml(text: str | None) -> dict:
    """Tiny YAML subset parser (key: scalar | [a, b] | - item lists). Stdlib only, no PyYAML."""
    out: dict = {}
    if not text:
        return out
    key = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("-") and key:
            out.setdefault(key, [])
            if isinstance(out[key], list):
                out[key].append(line.lstrip()[1:].strip().strip('"\''))
            continue
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            key = k.strip()
            v = v.strip()
            if v == "":
                out[key] = []
            elif v.startswith("[") and v.endswith("]"):
                out[key] = [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
            elif v.lower() in ("true", "false"):
                out[key] = v.lower() == "true"
            elif v.isdigit():
                out[key] = int(v)
            else:
                out[key] = v.strip('"\'')
    return out
