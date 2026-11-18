"""Evals for the `test` skill.

test.mutation  HumanEval (Chen et al., 2021): the agent gets a correct implementation and
               must write a pytest suite for it. The suite must pass on the real code; its
               score is the share of non-equivalent mutants it kills. A mutant counts only
               if HumanEval's own hidden check also rejects it, so equivalent mutants are
               excluded.
test.tdd       TDD-Bench Verified (Ahmed et al., IBM 2024): real SWE-bench Verified issues.
               The agent must write a test that reproduces the issue before any fix exists.
               Graded fail-to-pass: the test must fail on the original code and pass once
               the upstream fix is applied. Runs locally (no Docker) on the sympy subset by
               default, since sympy needs only mpmath.
"""

from __future__ import annotations

import os
import re
import shutil
import zlib
from pathlib import Path

from ..agent import Conversation, install_skills, prompt_for_arm
from ..humaneval import run_check
from ..mutate import mutants
from ..workspace import (apply_patch, changed_files, fresh_dir, git, init_repo, run_pytest,
                         snapshot_repo, uv_venv)
from . import Task

# sympy 1.1+ test helpers need the legacy `py` library (newer pytest only shims it);
# sympy 1.0's helpers break when it is installed. Pick the environment by version.
SYMPY_DEPS = ["mpmath==1.3.0", "pytest<8", "py==1.11.0"]
SYMPY_1_0_DEPS = ["mpmath==1.3.0", "pytest<8"]


def sympy_env(version: str) -> Path:
    if version == "1.0":
        return uv_venv("sympy-1.0", "3.9", SYMPY_1_0_DEPS)
    return uv_venv("sympy", "3.9", SYMPY_DEPS)


def _env(python: Path, extra: dict | None = None) -> dict:
    return {"PATH": f"{python.parent}:{os.environ['PATH']}",
            "VIRTUAL_ENV": str(python.parent.parent)} | (extra or {})


def _test_files(files: list[str]) -> list[str]:
    return [f for f in files if f.endswith(".py") and
            (Path(f).name.startswith("test") or "/tests/" in f"/{f}")]


class MutationTests(Task):
    name = "test.mutation"
    skill = "test"
    data_file = "test_mutation"
    description = "HumanEval: write tests for correct code; score = mutants killed"
    primary = "mutation_score"
    metrics = {
        "mutation_score": (True, True),
        "suite_valid": (True, True),
        "n_tests": (None, False),
        "n_mutants": (None, False),
    }

    def run(self, inst, arm, ws, ctx, transcript):
        python = uv_venv("pytest", "3.12", ["pytest"])
        fresh_dir(ws)
        solution = inst["prompt"] + inst["canonical_solution"]
        (ws / "solution.py").write_text(solution)
        init_repo(ws)
        if arm != "baseline":
            install_skills(ws)
        task = (f"solution.py contains a working implementation of `{inst['entry_point']}`. "
                "Write a thorough pytest test suite for it in test_solution.py. Don't change "
                "solution.py.")
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript,
                            extra_env=_env(python))
        conv.send(prompt_for_arm(arm, self.skill, task))

        tests = _test_files(changed_files(ws))
        out = {"test_files": tests} | conv.summary()
        if not tests:
            return out | {"mutation_score": 0.0, "suite_valid": False, "n_tests": 0}
        grade = ws.parent / f"{ws.name}.grade"
        if grade.exists():
            shutil.rmtree(grade)
        grade.mkdir()
        for t in tests:
            (grade / t).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ws / t, grade / t)
        (grade / "solution.py").write_text(solution)
        code, _, counts = run_pytest(python, tests, grade, timeout=120)
        valid = code == 0 and counts["passed"] > 0
        out |= {"suite_valid": valid, "n_tests": counts["passed"] + counts["failed"]}
        if not valid:
            return out | {"mutation_score": 0.0}

        live = [m for m in mutants(solution, limit=60, seed=zlib.crc32(inst["id"].encode()))
                if not run_check(m, inst["test"], inst["entry_point"])]
        killed = 0
        for m in live:
            (grade / "solution.py").write_text(m)
            code, _, _ = run_pytest(python, tests, grade, timeout=60)
            killed += code != 0
        shutil.rmtree(grade, ignore_errors=True)
        return out | {"mutation_score": killed / len(live) if live else None,
                      "n_mutants": len(live), "killed": killed}


class TddRepro(Task):
    name = "test.tdd"
    skill = "test"
    data_file = "test_tdd"
    description = "TDD-Bench Verified (sympy): reproduce the issue with a fail-to-pass test"
    primary = "fail_to_pass"
    metrics = {
        "fail_to_pass": (True, True),
        "fails_before": (True, True),
        "passes_after": (True, True),
        "wrote_test": (True, True),
        "modified_source": (False, True),
    }
    repos = ("sympy/sympy",)

    def filter(self, rows):
        return [r for r in rows if r["repo"] in self.repos]

    def run(self, inst, arm, ws, ctx, transcript):
        python = sympy_env(inst["version"])
        snapshot_repo(inst["repo"], inst["base_commit"], ws)
        if arm != "baseline":
            install_skills(ws)
        env = _env(python, {"PYTHONPATH": str(ws)})
        task = ("A user reported this bug against the repository in the current directory:\n\n"
                f"<issue>\n{inst['original_issue']}\n</issue>\n\n"
                "Write a test in the project's existing test suite that reproduces it: the "
                "test must fail on the current code. Do not fix the bug. A Python environment "
                "with pytest is active; run tests with `python -m pytest <file>`.")
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript, extra_env=env)
        conv.send(prompt_for_arm(arm, self.skill, task))

        changed = changed_files(ws)
        tests = _test_files(changed)
        source = [f for f in changed if f not in tests and f.endswith(".py")]
        out = {"wrote_test": bool(tests), "modified_source": bool(source),
               "test_files": tests} | conv.summary()
        if not tests:
            return out | {"fail_to_pass": False, "fails_before": False, "passes_after": False}
        if source:  # grade the test against the original code, not the agent's fix
            # Reset each source file to the pre-agent revision (HEAD may hold the agent's
            # committed fix): restore files that existed there, even if deleted since,
            # and remove files the agent added.
            base = base_rev(ws)
            in_base = [f for f in source
                       if git("cat-file", "-e", f"{base}:{f}", cwd=ws, check=False) == ""]
            if in_base:
                git("checkout", base, "--", *in_base, cwd=ws)
            for f in set(source) - set(in_base):
                (ws / f).unlink(missing_ok=True)
        run_env = {"PYTHONPATH": str(ws)}
        g = grade_repro(python, ws, tests, inst["gold_patch"], {"PYTHONPATH": str(ws)})
        return out | g


def base_rev(ws: Path) -> str:
    """The snapshot's root commit: the repository as it was before the agent ran."""
    return git("rev-list", "--max-parents=0", "HEAD", cwd=ws).split()[0]


def grade_repro(python: Path, ws: Path, tests: list[str], gold_patch: str, env: dict) -> dict:
    """TDD-Bench fail-to-pass on the test functions added or edited in `tests`.

    Only those functions count: the upstream fix may legitimately break other
    pre-existing tests in the same file.
    """
    touched = _touched_tests(ws, tests)
    ids_before = _collect(python, tests, ws, env)
    before, out_before = _outcomes(python, tests, ws, env)
    # A test file that cannot even be collected on the old code (e.g. it imports a
    # symbol the fix introduces) counts as failing before, as in TDD-Bench.
    broken_before = {node for node, status in before.items()
                     if status == "ERROR" and "::" not in node}
    ok, msg = apply_patch(ws, gold_patch)
    if not ok:
        return {"fail_to_pass": None, "crashed": True,
                "error": f"gold patch did not apply: {msg[-500:]}"}
    ids_after = _collect(python, tests, ws, env)
    after, out_after = _outcomes(python, tests, ws, env)
    new_ids = {i for i in ids_before | ids_after if i.split("[")[0] in touched}
    # A test marked expected-failure or skipped after the fix proves nothing either way
    # (upstream sometimes adds @XFAIL tests alongside the real ones), so it is not counted.
    new_ids = {i for i in new_ids if after.get(i) not in ("XFAIL", "SKIPPED")}
    fails_before = any(before.get(i) in ("FAILED", "ERROR") or i.split("::")[0] in broken_before
                       for i in new_ids)
    passes_after = bool(new_ids) and all(after.get(i) == "PASSED" for i in new_ids)
    return {"fail_to_pass": fails_before and passes_after, "fails_before": fails_before,
            "passes_after": passes_after, "new_tests": sorted(new_ids),
            "before": {i: before.get(i) for i in new_ids},
            "after": {i: after.get(i) for i in new_ids},
            "before_tail": out_before[-1200:], "after_tail": out_after[-1200:]}


_RESULT = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED) (\S+)", re.M)


def _outcomes(python: Path, tests: list[str], ws: Path, env: dict) -> tuple[dict, str]:
    """Per-test outcome (PASSED/FAILED/ERROR/...) keyed by pytest node id."""
    _, out, _ = run_pytest(python, ["-rA", *tests], ws, timeout=900, env=env)
    return {node: status for status, node in _RESULT.findall(out)}, out


def _collect(python: Path, tests: list[str], ws: Path, env: dict) -> set[str]:
    _, out, _ = run_pytest(python, ["--collect-only", *tests], ws, timeout=600, env=env)
    return {l.strip() for l in out.splitlines() if "::" in l and not l.startswith(" ")}


def _touched_tests(ws: Path, tests: list[str]) -> set[str]:
    """Node-id prefixes (file::func or file::Class::func) of test functions with added or
    changed lines relative to the base commit."""
    import ast

    out = set()
    for t in tests:
        # Compare with the pre-agent revision so committed and uncommitted tests both count.
        base = base_rev(ws)
        diff = git("diff", "-U0", base, "--", t, cwd=ws, check=False)
        tracked = git("cat-file", "-e", f"{base}:{t}", cwd=ws, check=False) == ""
        changed = set()
        for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", diff, re.M):
            start, n = int(m.group(1)), int(m.group(2) or 1)
            # A pure deletion (n == 0) sits between lines start and start + 1,
            # e.g. removing an @XFAIL decorator above a test.
            changed.update(range(start, start + n) if n else (start, start + 1))
        try:
            tree = ast.parse((ws / t).read_text())
        except SyntaxError:
            continue

        def visit(nodes, prefix):
            for node in nodes:
                if isinstance(node, ast.ClassDef):
                    visit(node.body, f"{prefix}::{node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        node.name.startswith("test"):
                    first = min([d.lineno for d in node.decorator_list] + [node.lineno])
                    lines = range(first, (node.end_lineno or node.lineno) + 1)
                    if not tracked or changed.intersection(lines):
                        out.add(f"{prefix}::{node.name}")

        visit(tree.body, t)
    return out
