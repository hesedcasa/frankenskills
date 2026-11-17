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
import shutil
import zlib
from pathlib import Path

from ..agent import Conversation, install_skills, prompt_for_arm
from ..humaneval import run_check
from ..mutate import mutants
from ..workspace import (apply_patch, changed_files, fresh_dir, git, init_repo, run_pytest,
                         snapshot_repo, uv_venv)
from . import Task


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
        python = uv_venv("sympy", "3.9", ["mpmath==1.3.0", "pytest<8"])
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
            git("checkout", "HEAD", "--", *[f for f in source if (ws / f).exists()], cwd=ws,
                check=False)
        run_env = {"PYTHONPATH": str(ws)}
        code_before, out_before, _ = run_pytest(python, tests, ws, timeout=900, env=run_env)
        ok, msg = apply_patch(ws, inst["gold_patch"])
        if not ok:
            return out | {"fail_to_pass": None, "error": f"gold patch did not apply: {msg[-500:]}"}
        code_after, out_after, _ = run_pytest(python, tests, ws, timeout=900, env=run_env)
        fails_before = code_before == 1  # 1 = tests ran and some failed (not a usage error)
        passes_after = code_after == 0
        return out | {"fail_to_pass": fails_before and passes_after,
                      "fails_before": fails_before, "passes_after": passes_after,
                      "before_tail": out_before[-1200:], "after_tail": out_after[-1200:]}
