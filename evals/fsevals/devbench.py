"""DevBench project helpers: what the agent sees, the hidden tests, and how to run them."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from .workspace import fresh_dir, sh, uv_venv

DOC_KEYS = ("PRD", "UML_class", "UML_sequence", "architecture_design")
PYTHON = "3.10"


def _copy(src_root: Path, rel: str, dest_root: Path) -> None:
    for src in src_root.glob(rel):
        dst = dest_root / src.relative_to(src_root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def requirements_file(inst: dict) -> Path | None:
    dep = inst["config"].get("dependencies")
    p = Path(inst["path"]) / dep if dep else None
    return p if p and p.is_file() else None


def requirements(inst: dict) -> list[str]:
    p = requirements_file(inst)
    if not p:
        return []
    import sys

    stdlib = set(sys.stdlib_module_names) | {"unittest", "typing"}
    names = [l.strip() for l in p.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    # Some DevBench requirement files list standard-library modules (os, csv, ...).
    return [n for n in names if n.split(".")[0].split("=")[0].split("<")[0].split(">")[0]
            not in stdlib]


def setup_workspace(inst: dict, ws: Path, docs: tuple[str, ...] = DOC_KEYS) -> None:
    """Copy the docs and required data files, but no source code and no tests."""
    src, conf = Path(inst["path"]), inst["config"]
    fresh_dir(ws)
    for key in docs:
        if conf.get(key):
            _copy(src, conf[key], ws)
    for pattern in conf.get("required_files", []):
        _copy(src, pattern, ws)
    if conf.get("dependencies"):
        _copy(src, conf["dependencies"], ws)


def env_for(inst: dict) -> Path:
    """Shared venv with the project's declared dependencies plus pytest."""
    return uv_venv(f"devbench-{inst['id']}", PYTHON, requirements(inst) + ["pytest"])


def agent_env(python: Path) -> dict:
    import os

    bin_dir = str(python.parent)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "VIRTUAL_ENV": str(python.parent.parent)}


def reference_tests(inst: dict) -> dict[str, list[str]]:
    """Test function names in the hidden unit and acceptance tests, by file."""
    src, conf = Path(inst["path"]), inst["config"]
    out = {}
    for key in ("unit_tests", "acceptance_tests"):
        target = src / conf.get(key, "")
        files = [target] if target.is_file() else sorted(target.rglob("*.py")) if target.is_dir() else []
        for f in files:
            names = re.findall(r"def (test\w*)\(", f.read_text(errors="replace"))
            if names:
                out[str(f.relative_to(src))] = names
    return out


_PASSED = re.compile(r"^PASSED (\S+)", re.M)
_NODE = re.compile(r"^(?:PASSED|FAILED|ERROR) (\S+)", re.M)


class OracleError(RuntimeError):
    """The reference run could not be measured (timeout or crash); never cache it."""


def _pytest_nodes(python: Path, target: str, cwd: Path) -> tuple[set[str], int, str]:
    """Run pytest on one test dir/file; return (passed node ids, exit code, output).

    Raises subprocess.TimeoutExpired if the run times out, FileNotFoundError if the
    configured target is missing.
    """
    if not (cwd / target).exists():
        raise FileNotFoundError(f"configured test target {target} is missing")
    code, out = sh([str(python), "-m", "pytest", "-rA", "-q", "-p", "no:cacheprovider",
                    "-o", "addopts=", target], cwd=cwd, timeout=1200,
                   env={"PYTHONPATH": str(cwd)})
    return set(_PASSED.findall(out)), code, out


def _populate(inst: dict, ws: Path, grade_dir: Path) -> None:
    src, conf = Path(inst["path"]), inst["config"]
    if grade_dir.exists():
        shutil.rmtree(grade_dir)
    shutil.copytree(ws, grade_dir, ignore=shutil.ignore_patterns(".git", ".claude", ".pi", "__pycache__"))
    for key in ("unit_tests", "acceptance_tests"):
        if conf.get(key):
            _copy(src, conf[key], grade_dir)
    for pattern in conf.get("required_files", []):
        _copy(src, pattern, grade_dir)


# Bump when the oracle's measurement rules change, so stale cache entries are recomputed.
# v2: reference runs exiting other than 0/1, or with a missing target, are rejected.
ORACLE_VERSION = 2


def oracle_passing(inst: dict, python: Path) -> dict[str, list[str]]:
    """Hidden tests the reference implementation passes in this environment (cached).

    Tests that need something the sandbox lacks (e.g. live network) fail for the
    reference too, so they are excluded instead of counted against the agent.
    """
    from . import CACHE_DIR

    cache = CACHE_DIR / "devbench_oracle" / f"{inst['id']}.json"
    if cache.exists():
        cached = json.loads(cache.read_text())
        if cached.get("version") == ORACLE_VERSION:
            return {k: cached[k] for k in ("unit", "acceptance")}
    import tempfile

    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        grade = Path(tmp) / "grade"
        _populate(inst, Path(inst["path"]), grade)
        for kind in ("unit", "acceptance"):
            target = inst["config"].get(f"{kind}_tests")
            if not target:
                out[kind] = []
                continue
            try:
                passed, code, _ = _pytest_nodes(python, target, grade)
            except Exception as e:  # timeout, launch failure, missing target
                raise OracleError(f"reference run of {inst['id']} {kind} tests failed: {e}") from e
            # 0 = all passed, 1 = some failed: both are real measurements. Anything else
            # (interrupted, internal/usage error, nothing collected) is not.
            if code not in (0, 1):
                raise OracleError(f"reference run of {inst['id']} {kind} tests exited {code}")
            out[kind] = sorted(passed)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps({"version": ORACLE_VERSION} | out, indent=1))
    tmp.replace(cache)  # atomic: readers see the old file or the complete new one
    return out


def run_hidden_tests(inst: dict, ws: Path, grade_dir: Path, python: Path) -> dict:
    """Copy the agent's work plus the hidden tests into grade_dir and run both suites.

    Scores count only hidden tests that the reference implementation passes here.
    """
    oracle = oracle_passing(inst, python)
    _populate(inst, ws, grade_dir)
    res = {}
    try:
        for kind in ("unit", "acceptance"):
            target = inst["config"].get(f"{kind}_tests")
            want = set(oracle.get(kind, []))
            if not target or not want:
                continue
            try:
                passed, _, out = _pytest_nodes(python, target, grade_dir)
            except subprocess.TimeoutExpired as e:  # the agent's code hung the suite
                passed, out = set(), f"hidden {kind} tests did not finish: {e}"
            # Collection errors from the agent's code are failures, so any exit code
            # counts here; launch failures and missing targets propagate as crashes.
            res[f"{kind}_passed"], res[f"{kind}_total"] = len(passed & want), len(want)
            res[f"{kind}_tail"] = out[-1500:]
    finally:
        shutil.rmtree(grade_dir, ignore_errors=True)
    return res
