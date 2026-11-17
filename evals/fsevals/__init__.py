"""Evals for the frankenskills skills (spec, plan, build, test, review)."""

from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVALS_DIR.parent
SKILLS_DIR = REPO_ROOT / "skills"
CACHE_DIR = EVALS_DIR / ".cache"
SOURCES_DIR = CACHE_DIR / "sources"
DATA_DIR = CACHE_DIR / "data"
REPOS_DIR = CACHE_DIR / "repos"
RESULTS_DIR = EVALS_DIR / "results"

SKILL_NAMES = ("spec", "plan", "build", "test", "review")


class UsageLimitError(RuntimeError):
    """The account hit a usage or rate limit; results from here on are not valid."""


LIMIT_PATTERNS = ("hit your", "usage limit", "rate limit", "rate_limit", "overloaded")


def check_limit(text: str) -> None:
    low = (text or "").lower()[:500]
    if "overloaded" in low or ("limit" in low and any(p in low for p in LIMIT_PATTERNS)):
        raise UsageLimitError(text[:300])
