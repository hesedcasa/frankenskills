"""Eval for the `review` skill.

review.swe  SWE-bench Verified (Jimenez et al., 2024; OpenAI 2024) with real candidate
            patches from a public SWE-bench leaderboard submission (mini-SWE-agent +
            Gemini 3.5 Flash, Sept 2026). Each patch carries the official harness verdict:
            resolved (the hidden tests pass) or not. The reviewer sees the issue and the
            patch as the last commit and must approve or request changes. A correct review
            approves resolved patches and rejects unresolved ones; for rejected unresolved
            patches, a judge checks whether the review named the real defect, using the
            upstream fix and failing tests as ground truth.
"""

from __future__ import annotations

import re

from ..agent import Conversation, install_skills, prompt_for_arm
from ..judge import judge
from ..workspace import apply_patch, commit_all, git, snapshot_repo
from . import Task

VERDICT = re.compile(r"VERDICT:\s*\**\s*(APPROVE|REQUEST[_ ]CHANGES)", re.I)


class PatchReview(Task):
    name = "review.swe"
    skill = "review"
    data_file = "review"
    description = "SWE-bench Verified + real agent patches: approve resolved, catch broken"
    primary = "correct"
    metrics = {
        "correct": (True, True),
        "catch_rate": (True, True),
        "false_alarm_rate": (False, True),
        "localized_defect": (True, True),
        "verdict_given": (True, True),
    }

    def stratify(self, rows, n):
        good = [r for r in rows if r["resolved"]]
        bad = [r for r in rows if not r["resolved"]]
        out = []
        for g, b in zip(good, bad):
            out += [b, g]
        return out[:n]

    def run(self, inst, arm, ws, ctx, transcript):
        snapshot_repo(inst["repo"], inst["base_commit"], ws)
        (ws / "ISSUE.md").write_text(inst["original_issue"])
        git("add", "ISSUE.md", cwd=ws)
        git("commit", "-q", "--amend", "-m", "base", cwd=ws)
        ok, msg = apply_patch(ws, inst["candidate_patch"])
        if not ok:
            raise RuntimeError(f"candidate patch did not apply: {msg[-400:]}")
        title = inst["original_issue"].strip().splitlines()[0][:72]
        commit_all(ws, f"Fix: {title}")
        if arm != "baseline":
            install_skills(ws)
        task = ("The last commit in this repository (HEAD) is a proposed change meant to "
                "resolve the issue described in ISSUE.md. Review it (`git diff HEAD~1 HEAD`) "
                "and decide whether it should be merged as is. No test environment is set "
                "up; set one up if you need it. End your reply with a final line that is "
                "exactly `VERDICT: APPROVE` or `VERDICT: REQUEST_CHANGES`.")
        conv = Conversation(ws, arm, model=ctx.model, max_turns=ctx.max_turns,
                            timeout_s=ctx.timeout_s, transcript=transcript)
        r = conv.send(prompt_for_arm(arm, self.skill, task))

        hits = VERDICT.findall(r.text)
        verdict = None
        if hits:
            verdict = "approve" if hits[-1].upper() == "APPROVE" else "request_changes"
        else:
            j = judge("Did this code review approve the change for merge or request changes? "
                      f"\n\nREVIEW:\n{r.text[-6000:]}\n\n"
                      'Return {"verdict": "approve" | "request_changes" | "unclear"}.',
                      ctx.judge_model)
            verdict = j.get("verdict") if j.get("verdict") in ("approve", "request_changes") else None
        resolved = inst["resolved"]
        rejected = verdict == "request_changes"
        localized = None if resolved else False
        if not resolved and rejected:
            j = judge(
                "A candidate patch for a GitHub issue FAILS the project's hidden tests. A "
                "reviewer rejected it. Did the review identify the actual reason the patch "
                "is wrong (the behavior the failing tests check, which the upstream fix gets "
                "right and the candidate does not)? Generic or unrelated complaints don't count.\n\n"
                f"ISSUE:\n{inst['original_issue'][:6000]}\n\n"
                f"CANDIDATE PATCH:\n{inst['candidate_patch'][:12000]}\n\n"
                f"UPSTREAM FIX:\n{inst['gold_patch'][:12000]}\n\n"
                f"FAILING TESTS: {inst['fail_to_pass'][:20]}\n\n"
                f"REVIEW:\n{r.text[-8000:]}\n\n"
                'Return {"identified_real_defect": bool, "reason": string}.',
                ctx.judge_model)
            localized = j.get("identified_real_defect")
        return {
            "resolved_label": resolved,
            "verdict": verdict,
            "verdict_given": verdict is not None,
            "correct": verdict is not None and (verdict == "approve") == resolved,
            "catch_rate": None if resolved else rejected,
            "false_alarm_rate": rejected if resolved else None,
            "localized_defect": localized if not resolved else None,
            "review_tail": r.text[-3000:],
        } | conv.summary()
