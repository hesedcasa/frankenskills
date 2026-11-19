"""Workspaces, repository snapshots, Python environments, and pytest runs."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from . import CACHE_DIR, REPOS_DIR

GIT_ENV = {
    "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@example.invalid",
    "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@example.invalid",
}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


# Inherited from a hook or wrapper, these would point our git calls at another repo.
_GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                      "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE")


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}


def sh(cmd, cwd: Path | None = None, timeout: int = 600, env: dict | None = None,
       check: bool = False, input: str | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env=_clean_env() | GIT_ENV | (env or {}), input=input,
                          shell=isinstance(cmd, str))
    out = proc.stdout + proc.stderr
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {cmd}\n{out[-2000:]}")
    return proc.returncode, out


def git(*args: str, cwd: Path, check: bool = True, timeout: int = 600) -> str:
    return sh(["git", *args], cwd=cwd, check=check, timeout=timeout)[1]


def fresh_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def init_repo(path: Path, message: str = "base", force: bool = False) -> None:
    """Make `path` a git repo whose only commit is its current contents.

    force=True also commits files matched by .gitignore (an upstream snapshot can
    legitimately track such files).
    """
    git("init", "-q", "-b", "main", cwd=path)
    git("add", "-A", *(["--force"] if force else []), cwd=path)
    git("commit", "-q", "--allow-empty", "-m", message, cwd=path)


def commit_all(path: Path, message: str) -> str:
    git("add", "-A", cwd=path)
    git("commit", "-q", "--allow-empty", "-m", message, cwd=path)
    return git("rev-parse", "HEAD", cwd=path).strip()


def repo_cache(repo: str) -> Path:
    """A blobless clone of github.com/<repo>, shared by every instance of that repo."""
    dest = REPOS_DIR / repo.replace("/", "__")
    with _lock(repo):
        if not (dest / ".git").exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            sh(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                f"https://github.com/{repo}.git", str(dest)], timeout=3600, check=True)
    return dest


def snapshot_repo(repo: str, commit: str, dest: Path) -> Path:
    """Write the tree at `commit` into `dest` as a brand-new single-commit repo.

    Files come straight from the cached clone via `git checkout-index` with a
    throwaway index, so git itself handles paths and symlinks exactly as in the
    upstream tree (no archive extraction). The new repo has no upstream history,
    so the agent cannot `git log` its way to the fix.
    """
    cache = repo_cache(repo)
    fresh_dir(dest)
    with _lock(repo), tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        base = ["git", "--git-dir", str(cache / ".git"), "--work-tree", str(dest)]
        sh([*base, "read-tree", commit], env=env, check=True, timeout=3600)
        sh([*base, "checkout-index", "--all", "--force"], env=env, check=True, timeout=3600)
    init_repo(dest, "base", force=True)
    return dest


def apply_patch(path: Path, patch: str) -> tuple[bool, str]:
    code, out = sh(["git", "apply", "--whitespace=nowarn", "-"], cwd=path, input=patch)
    if code != 0:
        code, out = sh(["patch", "-p1", "--forward", "--batch"], cwd=path, input=patch)
    return code == 0, out


# ---------------------------------------------------------------- python envs

def uv_venv(key: str, python: str, packages: list[str]) -> Path:
    """A cached virtualenv identified by `key`. Returns its python executable."""
    root = CACHE_DIR / "venvs" / key
    py = root / "bin" / "python"
    with _lock(f"venv:{key}"):
        if not (root / ".ready").exists():
            fresh_dir(root)
            sh(["uv", "venv", "-q", "--python", python, str(root)], check=True, timeout=1800)
            if packages:
                sh(["uv", "pip", "install", "-q", "--python", str(py), *packages],
                   check=True, timeout=3600)
            (root / ".ready").write_text("ok")
    return py


_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")


def pytest_counts(output: str) -> dict:
    counts = {"passed": 0, "failed": 0, "error": 0}
    tail = output[-4000:]
    for n, kind in _SUMMARY.findall(tail):
        kind = "error" if kind.startswith("error") else kind
        if kind in counts:
            counts[kind] = max(counts[kind], int(n))
    counts["total"] = counts["passed"] + counts["failed"] + counts["error"]
    return counts


def run_pytest(python: Path, args: list[str], cwd: Path, timeout: int = 900,
               env: dict | None = None) -> tuple[int, str, dict]:
    try:
        code, out = sh([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-o", "addopts=", *args], cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, "timeout", {"passed": 0, "failed": 0, "error": 1, "total": 1}
    return code, out, pytest_counts(out)


def changed_files(path: Path) -> list[str]:
    """Files added or modified relative to the first commit, including untracked ones."""
    first = git("rev-list", "--max-parents=0", "HEAD", cwd=path).split()[0]
    tracked = git("diff", "--name-only", first, cwd=path).split()
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=path).split()
    return sorted({f for f in tracked + untracked if not f.startswith(".claude/")})


def n_commits(path: Path) -> int:
    return int(git("rev-list", "--count", "HEAD", cwd=path).strip())
