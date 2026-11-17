"""Download the pinned public datasets and normalize them into JSONL files.

Every source is a public GitHub repository pinned to a commit, so results are
reproducible. Nothing here needs Hugging Face or Docker.

    python -m fsevals.fetch            # fetch everything
    python -m fsevals.fetch --only review
"""

from __future__ import annotations

import argparse
import ast
import gzip
import json
import subprocess
from pathlib import Path

from . import DATA_DIR, SOURCES_DIR

# name -> (url, commit, sparse paths or None)
SOURCES = {
    "humanevalcomm": (
        "https://github.com/jie-jw-wu/human-eval-comm.git",
        "794a91f3c520e3939b8361e9f4ae927c25756a6e",
        ["/Benchmark/HumanEvalComm_v2.jsonl", "/Benchmark/HumanEval.jsonl", "/LICENSE"],
    ),
    "ambig_swe": (
        "https://github.com/sani903/InteractiveSWEAgents.git",
        "00421fe393380d916b9a17b9874949a5c41528cc",
        ["/LLM_underspecificity_annotation.xlsx", "/LICENSE"],
    ),
    "devbench": (
        "https://github.com/open-compass/DevBench.git",
        "bb593c1f9c535ff0dde0c9f4807d58c9566c3a6c",
        ["/benchmark_data/python/", "/LICENSE"],
    ),
    "tddbench": (
        "https://github.com/IBM/TDD-Bench-Verified.git",
        "3df8be066e486789d0b8e0d2865a3a4422b4560f",
        ["/id_list.txt", "/LICENSE"],
    ),
    "swe_experiments": (
        "https://github.com/SWE-bench/experiments.git",
        "40f164d5b8f1d249bf95a6df8b74b577fd8e519d",
        ["/evaluation/verified/20260901_mini-v2.4.2_gemini-3-5-flash/per_instance_details.json"],
    ),
    "agent_patches": (
        "https://github.com/john-b-yang/20260901_mini-v2.4.2_gemini-3-5-flash.git",
        "2f6637a2557da1f7b5f2b583ab7090a077bbeed2",
        ["/all_preds.jsonl"],
    ),
}

HEC_VARIANTS = {
    "1a": "ambiguity",
    "1c": "inconsistency",
    "1p": "incompleteness",
    "2ac": "ambiguity+inconsistency",
    "2ap": "ambiguity+incompleteness",
}


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def fetch_source(name: str) -> Path:
    url, commit, sparse = SOURCES[name]
    dest = SOURCES_DIR / name
    if (dest / ".fetched").exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        _git("init", "-q", cwd=dest)
        _git("remote", "add", "origin", url, cwd=dest)
    if sparse:
        _git("sparse-checkout", "set", "--no-cone", *sparse, cwd=dest)
    _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", commit, cwd=dest)
    _git("checkout", "-q", "FETCH_HEAD", cwd=dest)
    (dest / ".fetched").write_text(commit)
    print(f"fetched {name} @ {commit[:10]}")
    return dest


def _write(name: str, rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{name}.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {path.relative_to(DATA_DIR.parent.parent)} ({len(rows)} rows)")


def _ambig_frame():
    import pandas as pd

    src = fetch_source("ambig_swe")
    df = pd.read_excel(src / "LLM_underspecificity_annotation.xlsx")
    return df.fillna("")


def _as_list(v) -> list:
    if isinstance(v, list):
        return v
    if not v:
        return []
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return ast.literal_eval(v)
    except (ValueError, SyntaxError):
        # Excel truncates cells at 32,767 chars; keep every complete entry.
        import re

        return re.findall(r'"((?:[^"\\]|\\.)*)"', v)


def _swe_row(r) -> dict:
    return {
        "instance_id": r["instance_id"],
        "repo": r["repo"],
        "base_commit": r["base_commit"],
        "version": str(r["version"]),
        "original_issue": r["original_issue"],
        "underspecified_issue": r["problem_statement"],
        "missing_information": r["missing_information"],
        "gold_patch": r["patch"],
        "test_patch": r["test_patch"],
        "fail_to_pass": _as_list(r["FAIL_TO_PASS"]),
        "pass_to_pass": _as_list(r["PASS_TO_PASS"]),
    }


def build_spec() -> None:
    src = fetch_source("humanevalcomm")
    rows = []
    for line in (src / "Benchmark/HumanEvalComm_v2.jsonl").read_text().splitlines():
        p = json.loads(line)
        rows.append({
            "id": f"{p['name']}::original", "name": p["name"], "variant": "original",
            "clarification_type": "none", "ambiguous": False,
            "prompt": p["prompt"], "original_prompt": p["prompt"],
            "entry_point": p["entry_point"], "test_case": p["test_case"],
        })
        for v, kind in HEC_VARIANTS.items():
            if p.get(f"prompt{v}"):
                rows.append({
                    "id": f"{p['name']}::{v}", "name": p["name"], "variant": v,
                    "clarification_type": kind, "ambiguous": True,
                    "prompt": p[f"prompt{v}"], "original_prompt": p["prompt"],
                    "entry_point": p["entry_point"], "test_case": p["test_case"],
                })
    _write("spec_clarify", rows)
    df = _ambig_frame()
    _write("spec_swe", [_swe_row(r) for _, r in df.iterrows() if r["missing_information"]])


def build_devbench() -> None:
    src = fetch_source("devbench")
    rows = []
    for proj in sorted((src / "benchmark_data/python").iterdir()):
        cfg = proj / "repo_config.json"
        if not cfg.exists():
            continue
        conf = json.loads(cfg.read_text())
        rows.append({"id": proj.name, "language": "python", "path": str(proj), "config": conf})
    _write("devbench", rows)


def build_test() -> None:
    src = fetch_source("humanevalcomm")
    raw = (src / "Benchmark/HumanEval.jsonl").read_text()
    rows = [json.loads(l) for l in raw.splitlines() if l.strip()]
    _write("test_mutation", [{
        "id": r["task_id"], "prompt": r["prompt"], "canonical_solution": r["canonical_solution"],
        "test": r["test"], "entry_point": r["entry_point"],
    } for r in rows])

    ids = set(fetch_source("tddbench").joinpath("id_list.txt").read_text().split())
    df = _ambig_frame()
    _write("test_tdd", [_swe_row(r) for _, r in df.iterrows() if r["instance_id"] in ids])


def build_review() -> None:
    labels_src = fetch_source("swe_experiments")
    labels = json.loads(next(labels_src.rglob("per_instance_details.json")).read_text())
    preds_src = fetch_source("agent_patches")
    preds = {}
    for line in (preds_src / "all_preds.jsonl").read_text().splitlines():
        p = json.loads(line)
        preds[p["instance_id"]] = p
    df = _ambig_frame()
    rows = []
    for _, r in df.iterrows():
        iid = r["instance_id"]
        p = preds.get(iid)
        if not p or not (p.get("model_patch") or "").strip() or iid not in labels:
            continue
        row = _swe_row(r)
        row["candidate_patch"] = p["model_patch"]
        row["candidate_model"] = p.get("model_name_or_path", "")
        row["resolved"] = str(labels[iid]["resolved"]).lower() == "true"
        rows.append(row)
    _write("review", rows)


BUILDERS = {"spec": build_spec, "plan": build_devbench, "build": build_devbench,
            "test": build_test, "review": build_review}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=sorted(BUILDERS), action="append")
    args = ap.parse_args(argv)
    done = set()
    for name in args.only or sorted(BUILDERS):
        fn = BUILDERS[name]
        if fn not in done:
            fn()
            done.add(fn)


if __name__ == "__main__":
    main()
