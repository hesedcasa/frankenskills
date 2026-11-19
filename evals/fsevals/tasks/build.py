"""Eval for the `build` skill.

build.devbench      DevBench implementation track: the agent gets the PRD, UML diagrams,
                    and architecture design (all approved) and must implement the project.
                    The hidden unit and acceptance tests from DevBench are then run against
                    its code. Process metrics come from the transcript and git history.
build.bigcodebench  BigCodeBench (Hugging Face): the agent gets an approved task spec
                    (instruct_prompt) and must implement it in solution.py. Graded by
                    BigCodeBench's hidden unittest suite plus test-first process metrics.
"""

from __future__ import annotations

import re

from ..agent import Conversation, install_skills, prompt_for_arm
from ..bigcodebench import agent_env as bcb_agent_env
from ..bigcodebench import env_for as bcb_env_for
from ..bigcodebench import run_tests as bcb_run_tests
from ..devbench import agent_env, env_for, run_hidden_tests, setup_workspace
from ..judge import classify_turn
from ..workspace import changed_files, fresh_dir, init_repo, n_commits
from . import Task

AUTO_APPROVE = ("Approved. Go ahead and implement everything now, without further "
                "check-ins. Make your own calls on anything unresolved.")
MAX_ROUNDS = 4
TEST_FILE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$|(^|/)tests?/")


_SHELL_WRITE = re.compile(
    r"""(?:>>?|\btee\s+(?:-a\s+)?)\s*['"]?([\w./-]+\.py)\b"""
    r"""|open\(\s*['"]([\w./-]+\.py)['"]\s*,\s*['"][wa]""")


def written_paths(call: dict) -> list[str]:
    """Files a tool call writes: Write/Edit targets and shell redirections in Bash."""
    if call["name"] in ("Write", "Edit", "NotebookEdit"):
        return [str(call["input"].get("file_path", ""))]
    if call["name"] == "Bash":
        cmd = str(call["input"].get("command", ""))
        return [a or b for a, b in _SHELL_WRITE.findall(cmd)]
    return []


def _first_write(tool_calls, pred):
    for i, c in enumerate(tool_calls):
        if any(pred(p) for p in written_paths(c)):
            return i
    return None


class DevBenchBuild(Task):
    name = "build.devbench"
    skill = "build"
    data_file = "devbench"
    # TextCNN needs torch and Hugging Face downloads at test time; opt in with --ids.
    excluded = {"TextCNN"}

    def filter(self, rows):
        return [r for r in rows if r["id"] not in self.excluded]
    description = "DevBench docs -> working project, scored by hidden unit + acceptance tests"
    primary = "hidden_pass_rate"
    metrics = {
        "hidden_pass_rate": (True, True),
        "unit_pass_rate": (True, True),
        "acceptance_pass_rate": (True, True),
        "test_first": (True, True),
        "agent_test_files": (None, False),
        "commits": (None, False),
    }

    def run(self, inst, arm, ws, ctx, transcript):
        setup_workspace(inst, ws)
        init_repo(ws)
        if arm != "baseline":
            install_skills(ws)
        python = env_for(inst)
        task = ("The docs in this repository (PRD, UML class and sequence diagrams, "
                "architecture design) are the approved spec for a Python project. Implement "
                "the whole project in this repository, following the architecture design's "
                "file layout and names. A virtualenv with the declared dependencies and "
                "pytest is already active.")
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript,
                            extra_env=agent_env(python))
        msg = prompt_for_arm(arm, self.skill, task)
        for _ in range(MAX_ROUNDS):
            r = conv.send(msg)
            if r.is_error or not classify_turn(r.text, ctx.judge_model).get("waiting_on_user"):
                break
            msg = AUTO_APPROVE

        agent_files = changed_files(ws)
        commits = n_commits(ws) - 1
        res = run_hidden_tests(inst, ws, ws.parent / f"{ws.name}.grade", python)
        up, ut = res.get("unit_passed", 0), res.get("unit_total", 0)
        if not ut and not res.get("acceptance_total"):
            raise RuntimeError(f"no hidden tests to grade {inst['id']} (empty oracle)")
        ap, at = res.get("acceptance_passed", 0), res.get("acceptance_total", 0)
        t_test = _first_write(conv.tool_calls, lambda p: bool(TEST_FILE.search(p)))
        t_src = _first_write(conv.tool_calls, lambda p: p.endswith(".py") and not TEST_FILE.search(p))
        return {
            "hidden_pass_rate": (up + ap) / (ut + at),
            "unit_pass_rate": up / ut if ut else None,
            "acceptance_pass_rate": ap / at if at else None,
            "test_first": None if t_src is None else (t_test is not None and t_test < t_src),
            "agent_test_files": sum(bool(TEST_FILE.search(f)) for f in agent_files),
            "commits": commits,
            "files_written": len(agent_files),
            "grading": res,
        } | conv.summary()


class BigCodeBenchBuild(Task):
    name = "build.bigcodebench"
    skill = "build"
    data_file = "bigcodebench"
    description = "BigCodeBench (Hugging Face): spec -> solution.py, scored by hidden unittest suite"
    primary = "pass_rate"
    metrics = {
        "pass_rate": (True, True),
        "all_pass": (True, True),
        "test_first": (True, True),
        "agent_test_files": (None, False),
        "commits": (None, False),
        "n_tests": (None, False),
    }

    def run(self, inst, arm, ws, ctx, transcript):
        fresh_dir(ws)
        init_repo(ws)
        if arm != "baseline":
            install_skills(ws)
        python = bcb_env_for(inst)
        task = (
            "Implement the following approved Python specification in `solution.py`. "
            "A virtualenv with the required libraries and pytest is already active.\n\n"
            f"{inst['instruct_prompt']}"
        )
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript,
                            extra_env=bcb_agent_env(python))
        msg = prompt_for_arm(arm, self.skill, task)
        for _ in range(MAX_ROUNDS):
            r = conv.send(msg)
            if r.is_error or not classify_turn(r.text, ctx.judge_model).get("waiting_on_user"):
                break
            msg = AUTO_APPROVE

        agent_files = changed_files(ws)
        commits = n_commits(ws) - 1
        sol = ws / "solution.py"
        if not sol.exists():
            pys = [ws / f for f in agent_files if f.endswith(".py") and not TEST_FILE.search(f)]
            sol = pys[0] if pys else sol
        if sol.exists():
            res = bcb_run_tests(sol.read_text(), inst["test"], python=python)
        else:
            res = {"passed": 0, "failed": 0, "errors": 1, "total": 1,
                   "pass_rate": 0.0, "all_pass": False, "output": "solution.py not found"}
        t_test = _first_write(conv.tool_calls, lambda p: bool(TEST_FILE.search(p)))
        t_src = _first_write(conv.tool_calls, lambda p: p.endswith(".py") and not TEST_FILE.search(p))
        return {
            "pass_rate": res["pass_rate"],
            "all_pass": res["all_pass"],
            "test_first": None if t_src is None else (t_test is not None and t_test < t_src),
            "agent_test_files": sum(bool(TEST_FILE.search(f)) for f in agent_files),
            "commits": commits,
            "n_tests": res["total"],
            "files_written": len(agent_files),
            "grading": res,
        } | conv.summary()

