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
