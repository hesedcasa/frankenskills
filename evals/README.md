# frankenskills evals

Measured evals for the five skills, built on public research datasets. Each eval runs Claude Code headlessly on real task instances in two or more **arms**, grades the result with executable checks where possible and an LLM judge only where necessary, and reports the paired difference against a no-skill baseline.

| Task | Skill | Dataset | Headline metric | Graded by |
|---|---|---|---|---|
| `spec.clarify` | spec | **HumanEvalComm** — 164 HumanEval problems rewritten to be ambiguous, inconsistent, or incomplete (5 variants each), plus the originals as controls | `pass_all` after the conversation | HumanEvalComm test cases (executed) |
| `spec.swe` | spec | **Ambig-SWE** — 496 SWE-bench Verified issues with details removed, each annotated with exactly what was removed | `info_recovery` | judge, item by item against the annotation |
| `plan.devbench` | plan | **DevBench** — 9 real Python projects with PRD, architecture, and hidden tests | `plan_score` = mean of rubric and hidden-test coverage | judge (7-criterion rubric; coverage against hidden test names) |
| `build.devbench` | build | **DevBench** implementation track | `hidden_pass_rate` | DevBench's hidden unit + acceptance tests (executed) |
| `test.mutation` | test | **HumanEval** — correct reference solutions | `mutation_score` | executed: suite must pass on real code; share of non-equivalent mutants killed |
| `test.tdd` | test | **TDD-Bench Verified** — 449 SWE-bench Verified issues (sympy subset of 67 runs locally) | `fail_to_pass` | executed: agent's test fails on the original code and passes with the upstream fix |
| `review.swe` | review | **SWE-bench Verified** + 441 real agent patches from a public leaderboard submission, each labeled resolved/unresolved by the official harness (359/82) | `correct` verdict | label from the official harness; judge checks defect localization |

## Arms

| Arm | Workspace | Prompt |
|---|---|---|
| `baseline` | stock Claude Code (its bundled skills included), frankenskills not installed | the task |
| `skill` | all five skills in `.claude/skills/` | `/<skill> ` + the task |
| `skill-implicit` | all five skills installed | the task (tests whether the skill's description triggers it) |

The arms differ only in whether frankenskills is installed. Every arm runs with project-only settings (no user plugins), no MCP servers, and **no web access** (several datasets are public and their answers are online).

## Quick start

```bash
cd evals
uv venv && uv pip install -e .
python -m fsevals.fetch                 # pinned GitHub sources -> .cache/data/*.jsonl
python -m fsevals.selfcheck             # oracle checks: graders score gold answers as correct
python -m fsevals.cli list
python -m fsevals.cli run test.mutation --n 20 --arms baseline,skill --workers 4
python -m fsevals.cli report results/test.mutation/<run>
```

Useful flags for `run`: `--model` (agent under test, default `sonnet`), `--judge-model` (default `opus`), `--user-model` (simulated user, defaults to the judge), `--reps` (repeat each instance and arm), `--ids` (exact instances), `--out` (reuse a run directory to resume after a crash), `--keep-workspaces` (keep each sandbox to inspect what the agent did).

Each run writes `config.json`, `records.jsonl` (one line per instance × arm × rep with every metric, cost, and the skills actually invoked), `transcripts/` (full stream-json for every agent call), and `report.md`.

## What each eval measures

**`spec.clarify`.** The agent sees a HumanEvalComm problem and is asked to implement it. A simulated user who holds the *original* problem answers questions and approvals, but only answers what was asked. Up to four rounds, then the agent is told "approved, implement it now". Metrics:
- `pass_all`: the final code passes HumanEvalComm's test cases. This is the paper's Pass@1-after-communication.
- `asked_when_ambiguous`: the agent asked a question on a modified problem. Higher is better.
- `asked_when_clear`: the agent asked on an unmodified control. Lower is better: over-asking is a cost.
- `question_quality`: 1–3, does the question target what was changed.
- `code_before_approval`: wrote `.py` before being told to implement. The spec skill's gate says it shouldn't.

**`spec.swe`.** The agent gets the repository at the issue's base commit and the underspecified issue, and must write `SPEC.md`. The simulated user holds the full original issue. A judge checks each annotated missing item against the spec (`info_recovery`), plus `testable_criteria`, `asked_questions`, and `touched_code` (any non-doc file changed, which is a gate violation).

**`plan.devbench`.** The agent gets only the PRD, treated as the approved spec, and writes `PLAN.md`. The judge scores 7 criteria from the plan skill's contract (decomposition, named tests, verification commands, ordering, interfaces, no placeholders, executable without questions). `test_coverage` is the share of DevBench's hidden test functions whose behavior the plan commits to building and testing. `wrote_code` should be 0.

**`build.devbench`.** The agent gets PRD, UML, and architecture docs plus a virtualenv with the declared dependencies, and implements the project. If it stops to ask for approval, the user replies "approved, go ahead" (at most 4 rounds). Then DevBench's hidden unit and acceptance tests run against its code. Process metrics: `test_first` (first test file written before first source file), `agent_test_files`, `commits`.

**`test.mutation`.** The agent writes `test_solution.py` for a correct HumanEval solution. The suite must pass on that solution (`suite_valid`). Then up to 15 AST mutants are generated (flipped comparisons, swapped operators, off-by-one constants, dropped `not`, `return None`, `and`↔`or`). Only mutants that HumanEval's own `check()` rejects are kept, so equivalent mutants never count against the suite. `mutation_score` is the share killed.

**`test.tdd`.** The agent gets the repository at the issue's base commit and the issue text, and must write a reproducing test without fixing the bug. Grading follows TDD-Bench: any source edits are reverted, the agent's test files are run (they must fail), the upstream fix is applied, and they run again (they must pass).

**`review.swe`.** The candidate patch is committed on top of the base commit with `ISSUE.md`, and the agent reviews `HEAD~1..HEAD` and ends with `VERDICT: APPROVE|REQUEST_CHANGES`. Ground truth is the official SWE-bench harness result for that patch. Metrics: `correct`, `catch_rate` (unresolved patches rejected), `false_alarm_rate` (resolved patches rejected), and `localized_defect` (rejected *for the real reason*, judged against the upstream fix and failing tests). Sampling alternates resolved and unresolved patches, so the set is balanced.

## Reading results

`report` prints per-arm means with 95% bootstrap CIs, then the paired difference against baseline on the same instances: ▲ means significantly better, ▼ significantly worse, · means the CI includes zero. Agent runs are noisy, so use `--reps 3` and at least 20–30 instances before drawing conclusions. Cost per record is in `cost_usd`, and the build and SWE tasks are the expensive ones.

Check `skills_invoked` in the records. In the `skill` arm it should contain the target skill. In `skill-implicit` it tells you how often the description alone triggered the skill.

## Datasets and pins

All sources are public GitHub repositories pinned to a commit in `fsevals/fetch.py`. Hugging Face is not required (and is unreachable in some sandboxes): SWE-bench Verified fields come from the Ambig-SWE release, which ships all 500 instances.

| Source | Repo @ commit | License | Paper |
|---|---|---|---|
| HumanEvalComm | `jie-jw-wu/human-eval-comm` @ `794a91f` | see repo | Wu & Fard, *Benchmarking the Communication Competence of Code Generation for LLMs and LLM Agents*, TOSEM 2025 ([arXiv 2406.00215](https://arxiv.org/abs/2406.00215)) |
| Ambig-SWE | `sani903/InteractiveSWEAgents` @ `00421fe` | MIT (OpenHands fork) | Vijayvargiya et al., *Interactive Agents to Overcome Underspecificity in Software Engineering*, ICLR 2026 ([arXiv 2502.13069](https://arxiv.org/abs/2502.13069)) |
| DevBench | `open-compass/DevBench` @ `bb593c1` | Apache-2.0 | Li et al., *DevBench: A Comprehensive Benchmark for Software Development*, 2024 ([arXiv 2403.08604](https://arxiv.org/abs/2403.08604)) |
| TDD-Bench Verified | `IBM/TDD-Bench-Verified` @ `3df8be0` | Apache-2.0 | Ahmed et al., *TDD-Bench Verified*, 2024 ([arXiv 2412.02883](https://arxiv.org/abs/2412.02883)) |
| SWE-bench Verified labels | `SWE-bench/experiments` @ `40f164d` | see repo | Jimenez et al., *SWE-bench*, ICLR 2024 |
| Candidate patches | `john-b-yang/20260901_mini-v2.4.2_gemini-3-5-flash` @ `2f6637a` | see repo | mini-SWE-agent leaderboard submission |
| HumanEval | via HumanEvalComm repo | MIT | Chen et al., 2021 |

The datasets are downloaded into `evals/.cache/`, which is git-ignored. They are not redistributed here.

## Results

See [RESULTS.md](RESULTS.md) for the first full run.

## Validation status

Oracle checks (`python -m fsevals.selfcheck`), run when the suite was built:

| Grader | Oracle | Result |
|---|---|---|
| `spec.clarify` | HumanEval reference solutions vs HumanEvalComm cases | 163/164 pass (HumanEval/32 excluded: its cases are a script template) |
| `test.mutation` | reference passes `check()`; mutants killable by `check()` | min 1, mean 8.2 killable mutants per problem |
| `build.devbench` | reference implementation / empty workspace | 100% / 0% on every project (network-only tests excluded) |
| `test.tdd` | upstream test patch as the "agent's test" | 4/4 fail-to-pass |
| `review.swe` | candidate patches apply to the base commit | 4/4 |

Every task has also completed end to end with the agent in both arms (1–2 instances each). Those smoke runs only prove the pipeline works. They are far too small to say anything about the skills.

## Known limits

- **Simulated users and judges are models.** HumanEvalComm and Ambig-SWE both use simulated users too. Keep `--judge-model` fixed across runs you compare, and spot-check `records.jsonl`, which stores every conversation and judge rationale.
- **Local execution only, no Docker.** `test.tdd` runs the sympy subset (67 of 449) because sympy needs only `mpmath`. Other repositories need the official TDD-Bench Docker harness (`tddbench`). `review.swe` does not need execution, since labels are precomputed.
- **DevBench unit tests sometimes import helpers the docs never name** (e.g. lice's tests import `valid_year`). One missing name fails the whole unit file at import, for both arms alike. Read `unit_pass_rate` with that in mind; `acceptance_pass_rate` tests only documented, black-box behavior.
- **DevBench is small** (9 Python projects here). TextCNN is excluded by default: it needs torch and Hugging Face downloads at test time. Use `--reps` for tighter estimates.
- **Single candidate model for review.** Patches come from one leaderboard run. To diversify, add another submission's `all_preds.jsonl` and per-instance labels in `fetch.py`.
- **Excel truncation.** Ambig-SWE ships as `.xlsx`, which truncates a few very long `PASS_TO_PASS` lists. Those lists are unused by the graders.
