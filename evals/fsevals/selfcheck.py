"""Oracle checks: feed each grader a known-good answer and confirm it scores as correct.

Run this before trusting any eval numbers. No agent or judge calls are made.

    python -m fsevals.selfcheck [--n 3]
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from .devbench import env_for, run_hidden_tests
from .humaneval import run_cases, run_check
from .mutate import mutants
from .tasks import all_tasks
from .tasks.test import _test_files, grade_repro, sympy_env
from .workspace import (apply_patch, changed_files, commit_all, run_pytest, snapshot_repo,
                        uv_venv)


FAILURES: list[str] = []


def check_humaneval(n: int) -> None:
    t = all_tasks()["spec.clarify"]
    rows = [r for r in t.load() if r["variant"] == "original"][:n * 10]
    ok = 0
    sol_rows = {r["id"]: r for r in all_tasks()["test.mutation"].load()}
    with tempfile.TemporaryDirectory() as tmp:
        for r in rows:
            he = sol_rows[r["name"]]
            p = Path(tmp) / "solution.py"
            p.write_text(he["prompt"] + he["canonical_solution"])
            ok += run_cases(p, r["entry_point"], r["test_case"])["all_pass"]
    print(f"spec.clarify grader: canonical solutions pass HumanEvalComm cases {ok}/{len(rows)}")
    if ok != len(rows):
        FAILURES.append(f"spec.clarify: {len(rows) - ok} canonical solutions rejected")

    live_counts = []
    for he in list(sol_rows.values())[:n * 10]:
        src = he["prompt"] + he["canonical_solution"]
        assert run_check(src, he["test"], he["entry_point"]), he["id"]
        live = [m for m in mutants(src, limit=40) if not run_check(m, he["test"], he["entry_point"])]
        live_counts.append(len(live))
    print(f"test.mutation grader: canonical passes check; killable mutants per problem "
          f"min={min(live_counts)} mean={sum(live_counts)/len(live_counts):.1f}")


def check_devbench(n: int) -> None:
    t = all_tasks()["build.devbench"]
    for inst in t.filter(t.load())[:n]:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            shutil.copytree(inst["path"], ws)
            try:
                py = env_for(inst)
                res = run_hidden_tests(inst, ws, Path(tmp) / "grade", py)
            except Exception as e:
                print(f"build.devbench {inst['id']}: ENV FAILED {str(e)[:200]}")
                FAILURES.append(f"build.devbench {inst['id']}: environment failed")
                continue
            print(f"build.devbench {inst['id']}: reference implementation scores "
                  f"unit {res.get('unit_passed')}/{res.get('unit_total')}, "
                  f"acceptance {res.get('acceptance_passed')}/{res.get('acceptance_total')}")
            for kind in ("unit", "acceptance"):
                if res.get(f"{kind}_passed") != res.get(f"{kind}_total"):
                    FAILURES.append(f"build.devbench {inst['id']}: reference fails {kind} tests")


def check_tdd(n: int) -> None:
    task = all_tasks()["test.tdd"]
    good = 0
    insts = task.sample(n, 0)
    for inst in insts:
        with tempfile.TemporaryDirectory() as tmp:
            ws = snapshot_repo(inst["repo"], inst["base_commit"], Path(tmp) / "ws")
            apply_patch(ws, inst["test_patch"])  # the upstream test is a perfect answer
            tests = _test_files(changed_files(ws))
            py = sympy_env(inst["version"])
            g = grade_repro(py, ws, tests, inst["gold_patch"], {"PYTHONPATH": str(ws)})
            ok = bool(g["fail_to_pass"])
            good += ok
            print(f"test.tdd {inst['instance_id']}: upstream test "
                  f"{'fail-to-pass' if ok else 'NOT fail-to-pass ' + str(g.get('after'))}")
    print(f"test.tdd grader: {good}/{len(insts)} upstream tests are fail-to-pass")
    if good != len(insts):
        FAILURES.append(f"test.tdd: {len(insts) - good} upstream tests not fail-to-pass")


def check_review(n: int) -> None:
    task = all_tasks()["review.swe"]
    for inst in task.sample(n, 0):
        with tempfile.TemporaryDirectory() as tmp:
            ws = snapshot_repo(inst["repo"], inst["base_commit"], Path(tmp) / "ws")
            ok, _ = apply_patch(ws, inst["candidate_patch"])
            commit_all(ws, "candidate")
            print(f"review.swe {inst['instance_id']} resolved={inst['resolved']}: "
                  f"candidate applies={ok}")
            if not ok:
                FAILURES.append(f"review.swe {inst['instance_id']}: candidate patch does not apply")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--only", choices=["humaneval", "devbench", "tdd", "review"], action="append")
    args = ap.parse_args(argv)
    checks = {"humaneval": check_humaneval, "devbench": check_devbench, "tdd": check_tdd,
              "review": check_review}
    for name in args.only or checks:
        checks[name](args.n)
    if FAILURES:
        print("\nSELFCHECK FAILED:\n  " + "\n  ".join(FAILURES))
        raise SystemExit(1)
    print("\nselfcheck passed")


if __name__ == "__main__":
    main()
