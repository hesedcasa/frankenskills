"""Eval for the `plan` skill.

plan.devbench  DevBench (Li et al., 2024): real Python projects, each with a PRD, an
               architecture design, and hidden unit and acceptance tests. The agent gets
               only the PRD (treated as the approved spec) and must write PLAN.md. A judge
               scores the plan's structure, and checks how many of the behaviors the hidden
               tests exercise the plan already commits to testing.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..agent import Conversation, install_skills, prompt_for_arm
from ..devbench import reference_tests, setup_workspace
from ..judge import judge
from ..workspace import changed_files, init_repo
from . import Task

RUBRIC = {
    "decomposition": "Work is split into small, independently verifiable tasks, ideally vertical slices; no task is huge.",
    "named_tests": "Each task names specific tests with concrete inputs and expected values, not 'add tests'.",
    "verification_commands": "Each task gives the exact command(s) to run and the expected result.",
    "ordering": "Dependencies between tasks are explicit and the order is sound (foundations and risky parts early).",
    "interfaces": "Files, function/class names, and signatures that tasks share are stated exactly and consistently.",
    "no_placeholders": "No 'TBD', 'handle edge cases', 'add validation as needed' or similar lines that decide nothing.",
    "executable": "A competent engineer who never saw the PRD's author could execute the plan without asking questions.",
}


class DevBenchPlan(Task):
    name = "plan.devbench"
    skill = "plan"
    data_file = "devbench"
    # TextCNN needs torch and Hugging Face downloads at test time; opt in with --ids.
    excluded = {"TextCNN"}

    def filter(self, rows):
        return [r for r in rows if r["id"] not in self.excluded]
    description = "DevBench PRD -> PLAN.md: structure rubric + coverage of hidden-test behaviors"
    primary = "plan_score"
    metrics = {
        "plan_score": (True, True),
        "rubric_score": (True, True),
        "test_coverage": (True, True),
        "plan_written": (True, True),
        "wrote_code": (False, True),
    } | {f"rubric_{k}": (True, False) for k in RUBRIC}

    def run(self, inst, arm, ws, ctx, transcript):
        setup_workspace(inst, ws, docs=("PRD",))
        init_repo(ws)
        if arm != "baseline":
            install_skills(ws)
        prd = inst["config"]["PRD"]
        task = (f"{prd} is the approved spec for a new Python project in this repository. "
                "Write the implementation plan and save it as PLAN.md in the repository root. "
                "Don't write the code yet.")
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript)
        conv.send(prompt_for_arm(arm, self.skill, task))

        changed = changed_files(ws)
        plan_path = ws / "PLAN.md"
        if not plan_path.exists():
            mds = [ws / f for f in changed if f.lower().endswith(".md")]
            plan_path = max(mds, key=lambda p: p.stat().st_size) if mds else None
        plan = plan_path.read_text(errors="replace") if plan_path else ""
        out = {"plan_written": bool(plan.strip()),
               "wrote_code": any(f.endswith(".py") for f in changed),
               "plan_chars": len(plan)}
        if not plan.strip():
            return out | {"plan_score": 0.0, "rubric_score": 0.0, "test_coverage": 0.0} | conv.summary()

        prd_text = (Path(inst["path"]) / prd).read_text(errors="replace")
        r = judge(
            "Score this implementation plan written from the PRD below. For each criterion "
            "give 0 (absent), 1 (partial), or 2 (fully met).\n\nCRITERIA:\n"
            + "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
            + f"\n\nPRD:\n<<<\n{prd_text[:15000]}\n>>>\n\nPLAN:\n<<<\n{plan[:40000]}\n>>>\n\n"
            'Return {"scores": {criterion: 0|1|2}, "notes": string}.',
            ctx.judge_model)
        if "_judge_error" in r or not isinstance(r.get("scores"), dict):
            raise RuntimeError(f"rubric judge failed: {r.get('_judge_error', r)}")
        scores = {k: (r.get("scores") or {}).get(k) for k in RUBRIC}
        valid = [s for s in scores.values() if isinstance(s, (int, float))]
        rubric = sum(valid) / (2 * len(valid)) if valid else None

        ref = reference_tests(inst)
        names = [f"{f}::{t}" for f, ts in ref.items() for t in ts]
        cov = None
        if names:
            c = judge(
                "Below are the tests a hidden reference test suite runs against this project, "
                "and an implementation plan. For each test, decide whether the plan commits to "
                "building AND testing the behavior that test checks (by name or by clearly "
                "equivalent behavior). Infer each test's behavior from its file and name.\n\n"
                f"HIDDEN TESTS:\n" + "\n".join(names[:200])
                + f"\n\nPLAN:\n<<<\n{plan[:40000]}\n>>>\n\n"
                'Return {"covered": [test ids covered], "not_covered": [test ids]}.',
                ctx.judge_model)
            if "_judge_error" in c or not isinstance(c.get("covered"), list):
                raise RuntimeError(f"coverage judge failed: {c.get('_judge_error', c)}")
            covered = set(c.get("covered") or [])
            cov = len([n for n in names if n in covered]) / len(names)
        parts = [x for x in (rubric, cov) if x is not None]
        return out | {
            "plan_score": sum(parts) / len(parts) if parts else None,
            "rubric_score": rubric, "test_coverage": cov,
            "n_reference_tests": len(names),
            "judge_notes": r.get("notes"),
        } | {f"rubric_{k}": v for k, v in scores.items()} | conv.summary()
