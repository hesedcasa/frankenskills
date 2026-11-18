"""Evals for the `spec` skill.

spec.clarify  HumanEvalComm (Wu et al., TOSEM 2025): HumanEval problems rewritten to be
              ambiguous, inconsistent, or incomplete, plus the unmodified originals as a
              control. A simulated user who knows the original problem answers the
              agent's questions. After the conversation the agent is told to implement,
              and the code is run against HumanEvalComm's test cases.
spec.swe      Ambig-SWE (Vijayvargiya et al., ICLR 2026): SWE-bench Verified issues with
              key details removed, annotated with exactly what was removed. The agent
              must produce SPEC.md; a judge checks how much of the removed information
              the spec recovered.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from pathlib import Path

from ..agent import Conversation, install_skills, prompt_for_arm
from ..humaneval import run_cases
from ..judge import classify_turn, judge, simulated_user_reply
from ..workspace import changed_files, fresh_dir, init_repo, snapshot_repo
from . import Ctx, Task

MAX_ROUNDS = 4
IMPLEMENT_NOW = ("Approved. Please implement the function now in solution.py (a single "
                 "file; no tests or extra files needed). Don't ask any more questions.")


def _converse(conv: Conversation, first_msg: str, hidden_spec: str, ctx: Ctx) -> list[dict]:
    """Drive the conversation until the agent stops waiting on the user."""
    rounds = []
    msg = first_msg
    for _ in range(MAX_ROUNDS):
        r = conv.send(msg)
        cls = classify_turn(r.text, ctx.judge_model)
        rounds.append({"agent": r.text, "classification": cls})
        if not cls.get("waiting_on_user"):
            break
        # Asking only for sign-off means the spec phase is over. Stop here so that
        # approval doesn't carry the agent on into planning and building.
        if cls.get("requests_approval") and not cls.get("asks_questions"):
            break
        msg = simulated_user_reply(hidden_spec, r.text, ctx.user_model)
        rounds[-1]["user_reply"] = msg
    return rounds


class Clarify(Task):
    name = "spec.clarify"
    skill = "spec"
    data_file = "spec_clarify"
    description = "HumanEvalComm: ask when it matters, don't when it doesn't, then pass the tests"
    primary = "pass_all"
    # HumanEval/32's HumanEvalComm cases are a script template, not checkable here.
    excluded = {"HumanEval/32"}

    def filter(self, rows):
        return [r for r in rows if r["name"] not in self.excluded]
    metrics = {
        "pass_all": (True, True),
        "test_pass_rate": (True, True),
        "asked_when_ambiguous": (True, True),
        "asked_when_clear": (False, True),
        "question_quality": (True, False),
        "code_before_approval": (False, True),
        "rounds": (None, False),
    }

    def stratify(self, rows, n):
        groups = defaultdict(list)
        for r in rows:
            groups[r["variant"]].append(r)
        order = ["original", "1a", "1c", "1p", "2ac", "2ap"]
        picked = []
        for r in itertools.chain.from_iterable(itertools.zip_longest(*(groups[v] for v in order))):
            if r is not None:
                picked.append(r)
            if len(picked) == n:
                break
        return picked

    def run(self, inst, arm, ws, ctx, transcript):
        fresh_dir(ws)
        init_repo(ws)
        if arm != "baseline":
            install_skills(ws)
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript)
        task = f"I need this Python function implemented:\n\n```python\n{inst['prompt']}\n```"
        rounds = _converse(conv, prompt_for_arm(arm, self.skill, task), inst["original_prompt"], ctx)
        code_before = any(c["name"] in ("Write", "Edit", "NotebookEdit")
                          and str(c["input"].get("file_path", "")).endswith(".py")
                          for c in conv.tool_calls)
        conv.send(IMPLEMENT_NOW)

        sol = ws / "solution.py"
        if not sol.exists():
            pys = [ws / f for f in changed_files(ws) if f.endswith(".py")]
            sol = pys[0] if pys else sol
        res = run_cases(sol, inst["entry_point"], inst["test_case"]) if sol.exists() else \
            {"pass_rate": 0.0, "all_pass": False}

        first = rounds[0]["classification"]
        asked = bool(first.get("asks_questions"))
        quality = None
        if asked:
            q = judge(
                "A coding agent was given a modified programming problem and asked the "
                "user clarifying questions.\n\n"
                f"MODIFIED PROBLEM (what the agent saw):\n{inst['prompt']}\n\n"
                f"ORIGINAL PROBLEM (the true intent):\n{inst['original_prompt']}\n\n"
                f"AGENT'S QUESTIONS:\n{first.get('questions') or rounds[0]['agent'][-3000:]}\n\n"
                "Score the questions 1-3: 3 = they target exactly what the modification made "
                "ambiguous, inconsistent, or missing, so answering them recovers the original; "
                "2 = partly; 1 = irrelevant or generic. "
                'Return {"score": 1|2|3, "reason": string}.',
                ctx.judge_model)
            quality = q.get("score")
        return {
            "variant": inst["variant"],
            "pass_all": res["all_pass"],
            "test_pass_rate": res["pass_rate"],
            "asked_when_ambiguous": asked if inst["ambiguous"] else None,
            "asked_when_clear": None if inst["ambiguous"] else asked,
            "question_quality": quality,
            "code_before_approval": code_before,
            "rounds": len(rounds),
            "conversation": rounds,
        } | conv.summary()


class SweSpec(Task):
    name = "spec.swe"
    skill = "spec"
    data_file = "spec_swe"
    description = "Ambig-SWE: recover the information removed from a real issue into SPEC.md"
    primary = "info_recovery"
    metrics = {
        "info_recovery": (True, True),
        "asked_questions": (True, True),
        "spec_written": (True, True),
        "testable_criteria": (True, True),
        "touched_code": (False, True),
        "rounds": (None, False),
    }

    def run(self, inst, arm, ws, ctx, transcript):
        snapshot_repo(inst["repo"], inst["base_commit"], ws)
        if arm != "baseline":
            install_skills(ws)
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript)
        task = (f"This issue was reported against the repository in the current directory:\n\n"
                f"<issue>\n{inst['underspecified_issue']}\n</issue>\n\n"
                "Before anyone changes code, write a spec for resolving it and save it as "
                "SPEC.md in the repository root. I'm the reporter and can answer questions.")
        rounds = _converse(conv, prompt_for_arm(arm, self.skill, task), inst["original_issue"], ctx)

        changed = changed_files(ws)
        # Deleted files are "changed" too; only an existing file can be the spec.
        md = [f for f in changed if f.lower().endswith(".md") and (ws / f).is_file()]
        specs = [f for f in md if Path(f).name == "SPEC.md"]
        # Prefer a SPEC.md this run wrote: an unchanged root SPEC.md from the base
        # snapshot belongs to someone else.
        pick = "SPEC.md" if "SPEC.md" in md else (specs[0] if specs else (md[0] if md else None))
        spec_path = ws / pick if pick else None
        spec_text = spec_path.read_text(errors="replace") if spec_path else ""
        convo = "\n\n".join(f"AGENT: {r['agent'][-2500:]}\nUSER: {r.get('user_reply', '')}"
                            for r in rounds)
        g = judge(
            "An agent wrote a spec for a vaguely reported issue. Some information was removed "
            "from the original issue; check whether the agent recovered it (by asking, by "
            "reading the code, or by inference) and wrote it into the spec.\n\n"
            f"REMOVED INFORMATION (numbered items):\n{inst['missing_information']}\n\n"
            f"SPEC:\n<<<\n{spec_text[:20000] or '(no spec file written)'}\n>>>\n\n"
            f"CONVERSATION (for context only; credit only what is in the SPEC):\n{convo[:12000]}\n\n"
            'Return {"items": [{"item": int, "recovered": bool}], '
            '"testable_success_criteria": bool}. testable_success_criteria is true if the '
            "spec states concrete, checkable conditions for done.",
            ctx.judge_model)
        items = g.get("items") or []
        recovery = sum(bool(i.get("recovered")) for i in items) / len(items) if items else None
        return {
            "info_recovery": recovery,
            "asked_questions": bool(rounds[0]["classification"].get("asks_questions")),
            "spec_written": bool(spec_text.strip()),
            "testable_criteria": bool(g.get("testable_success_criteria")),
            "touched_code": any(not f.lower().endswith((".md", ".txt", ".rst")) for f in changed),
            "rounds": len(rounds),
            "judge": g,
            "conversation": rounds,
        } | conv.summary()
