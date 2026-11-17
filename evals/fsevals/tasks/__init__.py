"""Eval tasks. Each task runs one dataset instance in one arm and returns metrics."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from .. import DATA_DIR


@dataclass
class Ctx:
    run_dir: Path
    model: str | None
    judge_model: str | None
    user_model: str | None
    max_turns: int
    timeout_s: int
    keep_workspaces: bool


class Task:
    name = ""          # e.g. "spec.clarify"
    skill = ""         # which skill this evaluates
    data_file = ""     # JSONL under .cache/data
    description = ""
    # metric name -> (higher_is_better or None for neutral, is_rate)
    metrics: dict[str, tuple[bool, bool]] = {}
    primary = ""       # headline metric

    def load(self) -> list[dict]:
        path = DATA_DIR / f"{self.data_file}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} missing: run `python -m fsevals.fetch` first")
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    def instance_id(self, inst: dict) -> str:
        return inst.get("id") or inst["instance_id"]

    def sample(self, n: int | None, seed: int, ids: list[str] | None = None) -> list[dict]:
        rows = self.load()
        if ids:
            want = set(ids)
            return [r for r in rows if self.instance_id(r) in want]
        rows = self.filter(rows)
        random.Random(seed).shuffle(rows)
        return rows if n is None else self.stratify(rows, n)

    def filter(self, rows: list[dict]) -> list[dict]:
        return rows

    def stratify(self, rows: list[dict], n: int) -> list[dict]:
        return rows[:n]

    def run(self, inst: dict, arm: str, ws: Path, ctx: Ctx, transcript: Path) -> dict:
        raise NotImplementedError


def all_tasks() -> dict[str, Task]:
    from . import build, plan, review, spec, test

    tasks = [spec.Clarify(), spec.SweSpec(), plan.DevBenchPlan(), build.DevBenchBuild(),
             test.MutationTests(), test.TddRepro(), review.PatchReview()]
    return {t.name: t for t in tasks}
