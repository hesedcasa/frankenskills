"""Command line: fetch data, run evals, report results.

    fsevals list
    fsevals selfcheck [--n 3]
    fsevals fetch [--only review]
    fsevals run spec.clarify --n 20 --arms baseline,skill --workers 4
    fsevals report results/spec.clarify/<run>
"""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import RESULTS_DIR, UsageLimitError
from .agent import ARMS
from .tasks import Ctx, all_tasks


def cmd_list(_args) -> None:
    for name, t in all_tasks().items():
        print(f"{name:18} [{t.skill}]  {t.description}")


def cmd_fetch(args) -> None:
    from . import fetch

    fetch.main(sum((["--only", s] for s in args.only or []), []))


def _done_keys(records: Path) -> set:
    if not records.exists():
        return set()
    keys = set()
    for line in records.read_text().splitlines():
        r = json.loads(line)
        if not r.get("crashed"):
            keys.add((r["instance_id"], r["arm"], r["rep"]))
    return keys


def cmd_run(args) -> None:
    task = all_tasks()[args.task]
    arms = args.arms.split(",")
    for a in arms:
        if a not in ARMS:
            raise SystemExit(f"unknown arm {a}; choose from {ARMS}")
    run_dir = Path(args.out) if args.out else RESULTS_DIR / task.name / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(run_dir=run_dir, model=args.model, judge_model=args.judge_model,
              user_model=args.user_model or args.judge_model, max_turns=args.max_turns,
              timeout_s=args.timeout, keep_workspaces=args.keep_workspaces)
    insts = task.sample(args.n, args.seed, args.ids.split(",") if args.ids else None)
    (run_dir / "config.json").write_text(json.dumps({k: v for k, v in vars(args).items() if k != "fn"} | {
        "instances": [task.instance_id(i) for i in insts]}, indent=2))
    records = run_dir / "records.jsonl"
    done = _done_keys(records)
    jobs = [(i, a, r) for i in insts for a in arms for r in range(args.reps)
            if (task.instance_id(i), a, r) not in done]
    print(f"{task.name}: {len(insts)} instances x {len(arms)} arms x {args.reps} reps "
          f"= {len(jobs)} jobs to run -> {run_dir}")

    stop = threading.Event()

    def one(inst, arm, rep):
        iid = task.instance_id(inst)
        slug = f"{iid}__{arm}__{rep}".replace("/", "_").replace(":", "_")
        ws = run_dir / "workspaces" / slug
        t0 = time.time()
        rec = {"task": task.name, "skill": task.skill, "instance_id": iid, "arm": arm, "rep": rep}
        if stop.is_set():
            return rec | {"crashed": True, "error": "skipped: usage limit hit earlier in run"}
        try:
            rec |= task.run(inst, arm, ws, ctx, run_dir / "transcripts" / f"{slug}.jsonl")
        except UsageLimitError as e:
            stop.set()
            rec |= {"crashed": True, "error": f"usage limit: {e}"}
        except Exception as e:  # keep going; record the crash
            rec |= {"crashed": True, "error": f"{e}\n{traceback.format_exc()[-1500:]}"}
        rec["wall_s"] = round(time.time() - t0, 1)
        if not ctx.keep_workspaces and ws.exists():
            shutil.rmtree(ws, ignore_errors=True)
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as pool, records.open("a") as out:
        futs = [pool.submit(one, *j) for j in jobs]
        for k, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            out.write(json.dumps(rec) + "\n")
            out.flush()
            head = rec.get(task.primary, "CRASH" if rec.get("crashed") else "—")
            print(f"[{k}/{len(jobs)}] {rec['instance_id']} {rec['arm']}: "
                  f"{task.primary}={head} cost=${rec.get('cost_usd', 0):.2f}")
    from .report import report

    if stop.is_set():
        print("STOPPED: usage limit reached. Rerun the same command with --out "
              f"{run_dir} after the limit resets; finished records are kept.")
        raise SystemExit(3)
    print(report(run_dir))


def cmd_report(args) -> None:
    from .report import report

    print(report(Path(args.run_dir), write=True))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="fsevals", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    f = sub.add_parser("fetch")
    f.add_argument("--only", action="append", choices=["spec", "plan", "build", "test", "review"])
    f.set_defaults(fn=cmd_fetch)
    r = sub.add_parser("run")
    r.add_argument("task", choices=sorted(all_tasks()))
    r.add_argument("--arms", default="baseline,skill")
    r.add_argument("--n", type=int, default=10, help="instances to sample")
    r.add_argument("--ids", help="comma-separated instance ids (overrides --n)")
    r.add_argument("--reps", type=int, default=1, help="repetitions per instance and arm")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--model", default="sonnet", help="agent model under test")
    r.add_argument("--judge-model", default="opus")
    r.add_argument("--user-model", default=None, help="simulated user (defaults to judge)")
    r.add_argument("--max-turns", type=int, default=120)
    r.add_argument("--timeout", type=int, default=2400, help="seconds per agent call")
    r.add_argument("--workers", type=int, default=2)
    r.add_argument("--out", help="run directory (resume by reusing it)")
    r.add_argument("--keep-workspaces", action="store_true")
    r.set_defaults(fn=cmd_run)
    sc = sub.add_parser("selfcheck", help="oracle checks for the graders")
    sc.add_argument("rest", nargs=argparse.REMAINDER)
    sc.set_defaults(fn=lambda a: __import__("fsevals.selfcheck", fromlist=["main"]).main(a.rest))
    rp = sub.add_parser("report")
    rp.add_argument("run_dir")
    rp.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
