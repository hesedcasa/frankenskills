"""Run HumanEval-style checks against a solution file in a subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

_RUNNER = r'''
import ast, json, sys, inspect
src_path, entry, cases_src = sys.argv[1], sys.argv[2], sys.argv[3]
ns = {}
exec(compile(open(src_path).read(), src_path, "exec"), ns)
fn = ns.get(entry) or ns.get("candidate")
if fn is None:
    fns = [v for k, v in ns.items() if inspect.isfunction(v) and not k.startswith("_")
           and v.__code__.co_filename == src_path]
    fn = fns[-1] if fns else None
cases = ast.literal_eval(open(cases_src).read())
ok = 0
for c in cases:
    try:
        rel = c.get("relation", "==")
        if rel == "==":
            got = eval(f"__fn__({c['input']})", dict(ns, __fn__=fn))
            try:
                passed = got == eval(c["output"], dict(ns))
            except Exception:
                passed = False
            # HumanEvalComm stores string outputs unquoted ('xyzyx', '010010').
            passed = passed or (isinstance(got, str) and got == c["output"])
        else:  # HumanEvalComm stores a full boolean expression over `candidate`
            passed = bool(eval(rel, dict(ns, candidate=fn)))
        ok += passed
    except Exception:
        pass
print(json.dumps({"passed": ok, "total": len(cases), "found_function": fn is not None}))
'''


def run_cases(solution: Path, entry: str, test_case_literal, timeout: int = 60) -> dict:
    if not isinstance(test_case_literal, str):
        test_case_literal = repr(test_case_literal)
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "runner.py"
        runner.write_text(_RUNNER)
        cases = Path(tmp) / "cases.txt"
        cases.write_text(test_case_literal)
        try:
            proc = subprocess.run([sys.executable, str(runner), str(solution), entry, str(cases)],
                                  capture_output=True, text=True, timeout=timeout)
            res = json.loads(proc.stdout.strip().splitlines()[-1])
        except (subprocess.TimeoutExpired, IndexError, json.JSONDecodeError):
            res = {"passed": 0, "total": 1, "found_function": False}
    res["pass_rate"] = res["passed"] / max(res["total"], 1)
    res["all_pass"] = res["passed"] == res["total"] and res["total"] > 0
    return res


def run_check(solution_src: str, test_src: str, entry: str, timeout: int = 5) -> bool:
    """Original HumanEval `check(candidate)` harness. True if the solution passes."""
    prog = f"{solution_src}\n\n{test_src}\n\ncheck({entry})\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(prog)
    try:
        return subprocess.run([sys.executable, f.name], capture_output=True,
                              timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        Path(f.name).unlink(missing_ok=True)
