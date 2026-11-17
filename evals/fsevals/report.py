"""Summarize a run directory: per-arm metric means with 95% bootstrap CIs, and the
paired difference of each skill arm against baseline on the same instances."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .stats import bootstrap_ci, fmt, paired_diff
from .tasks import all_tasks


def _avg_by_instance(recs: list[dict], metric: str) -> dict:
    acc = defaultdict(list)
    for r in recs:
        v = r.get(metric)
        if isinstance(v, bool):
            v = float(v)
        if isinstance(v, (int, float)):
            acc[r["instance_id"]].append(float(v))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def report(run_dir: Path, write: bool = False) -> str:
    recs = [json.loads(l) for l in (run_dir / "records.jsonl").read_text().splitlines() if l]
    if not recs:
        return "no records"
    task = all_tasks()[recs[0]["task"]]
    arms = sorted({r["arm"] for r in recs}, key=lambda a: (a != "baseline", a))
    by_arm = {a: [r for r in recs if r["arm"] == a] for a in arms}
    metrics = dict(task.metrics) | {"cost_usd": (False, False)}

    lines = [f"## {task.name} — {task.description}", ""]
    for a in arms:
        crashed = sum(1 for r in by_arm[a] if r.get("crashed"))
        lines.append(f"- **{a}**: {len(by_arm[a])} records"
                     + (f", {crashed} crashed (excluded)" if crashed else ""))
    lines += ["", "| metric | " + " | ".join(arms) + " |",
              "|---|" + "---|" * len(arms)]
    per_inst = {}
    for m, (_hib, pct) in metrics.items():
        row = [f"{'**' if m == task.primary else ''}{m}{'**' if m == task.primary else ''}"]
        for a in arms:
            ok = [r for r in by_arm[a] if not r.get("crashed")]
            vals = _avg_by_instance(ok, m)
            per_inst[(a, m)] = vals
            row.append(fmt(*bootstrap_ci(list(vals.values())), pct=pct) + f" (n={len(vals)})")
        lines.append("| " + " | ".join(row) + " |")

    if "baseline" in arms and len(arms) > 1:
        lines += ["", "Paired difference vs baseline (same instances; ▲ better, ▼ worse, "
                  "· CI includes 0, Δ neutral metric):", "", "| metric | " + " | ".join(arms[1:]) + " |",
                  "|---|" + "---|" * (len(arms) - 1)]
        for m, (hib, pct) in metrics.items():
            row = [m]
            for a in arms[1:]:
                d = paired_diff(per_inst[("baseline", m)], per_inst[(a, m)])
                if d["mean"] is None:
                    row.append("—")
                    continue
                mark = "·"
                if hib is None:
                    mark = "Δ"
                elif d["lo"] is not None and (d["lo"] > 0 or d["hi"] < 0):
                    mark = "▲" if (d["mean"] > 0) == hib else "▼"
                row.append(f"{mark} {fmt(d['mean'], d['lo'], d['hi'], pct=pct)} (n={d['n']})")
            lines.append("| " + " | ".join(row) + " |")
    text = "\n".join(lines)
    if write:
        (run_dir / "report.md").write_text(text + "\n")
    return text
