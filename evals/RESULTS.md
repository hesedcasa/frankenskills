# Eval results — 2026-11-17/18

First full run of every eval. Agent: `sonnet` via Claude Code headless. Judge and simulated user: `opus`. Arms: `baseline` (stock Claude Code) vs `skill` (frankenskills installed, task prompt prefixed with `/<skill>`). 590 records, none crashed, about $68 of agent cost (judge calls not included).

Differences are paired by instance, with 95% bootstrap CIs. **Bold** marks a difference whose CI excludes zero.

## Headline

| Skill | Eval | Primary metric | Baseline | Skill | Paired Δ |
|---|---|---|---|---|---|
| spec | `spec.clarify` (n=60) | pass all tests after the conversation | 91.7% | 98.3% | **+6.7 pts** [+1.7, +13.3] |
| spec | `spec.swe` (n=30) | removed info recovered into SPEC.md | 73.8% | 66.1% | **−7.7 pts** [−13.9, −1.9] |
| plan | `plan.devbench` (9 × 3 reps) | plan score (rubric + hidden-test coverage) | 57.0% | 80.4% | **+23.4 pts** [+16.7, +31.3] |
| build | `build.devbench` (9 × 2 reps) | hidden tests passed | 61.6% | 58.7% | **−2.9 pts** [−5.5, −0.6] |
| test | `test.mutation` (n=40) | mutants killed | 97.5% | 97.5% | 0 (ceiling) |
| test | `test.tdd` (n=30, sympy) | fail-to-pass reproduction | 80.0% | 86.7% | +6.7 pts [−6.7, +20.0] |
| review | `review.swe` (n=40, 20 broken / 20 correct) | correct verdict | 65.0% | 62.5% | −2.5 pts [−17.5, +12.5] |

The skill arm costs more on every task: +$0.03 to +$0.17 per instance, between 1.4× and 3.2× baseline.

## What the evals show

**spec: it asks far more often, which helps on small ambiguous asks; on real issues it spends effort on a different part of the spec.**
- On HumanEvalComm's ambiguous problems it asked a clarifying question 94% of the time vs 34% (**+60 pts**). It wrote code before approval much less often (27% vs 55%, **−28 pts**). Final test pass rate rose (**+6.7 pts**).
- Cost: on the 10 unambiguous controls it asked unnecessarily 20% of the time vs 0% (CI includes 0, n is small). It took about 0.8 more rounds and cost 3.2× as much.
- On Ambig-SWE it kept to the spec gate far better: it edited code in 20% of runs vs 43% (**−23 pts**). But its specs recovered less of the specific removed information (**−7.7 pts**). Both arms asked questions in every run. *Inferred, not measured:* the skill's template pushes effort into structure (approaches, boundaries, out-of-scope) at the expense of the concrete details the reporter gave.

**plan: the clearest win.** The rubric score rose from 49% to 88%, improving significantly on all seven criteria. Verification commands moved the most (0.44 → 1.93 out of 2). Coverage of the hidden tests' behaviors rose 6 pts, but the CI includes 0. Neither arm wrote code.

**build: no benefit, slightly worse.** Hidden-test pass rate dropped by 2.9 pts, with a CI just excluding zero. Transcripts show why the skill isn't changing much: the agent loads `build`, then builds the whole project in one pass and says so. From one run: *"I skipped the plan, ledger and `review` steps of the build skill, so no independent review was done."* It does commit (1.3 commits vs 0). This is a gap in the skill: its process isn't followed when the task arrives as "implement the whole project" with no plan.

**test: no measurable effect, and the mutation eval is at ceiling.** Both arms kill 97.5% of mutants on HumanEval. The skill arm wrote half as many tests (32 vs 63) for the same kill rate. On TDD-Bench the skill reproduced 6.7 pts more issues, with a wide CI.

**review: more aggressive, not more accurate.** It caught more broken patches (55% vs 40%) and named the real defect more often (30% vs 20%), but neither difference is significant. It also rejected correct patches far more often (30% vs 10%, **+20 pts**). Overall accuracy was unchanged.

## Suggested skill changes, from these results

1. **build:** make the loop non-optional when no plan exists. Today the skill says to "write the 2–5 steps as a todo" for small work, and agents treat a whole project as small. Add an explicit rule: no plan file and more than ~3 files means stop and run `plan` first (or plan inline and commit the plan), then do the per-task test-first loop.
2. **review:** add a calibration step before `Request changes`. A finding must be reproduced (a failing run, or a concrete input → wrong output) to block a merge; anything unproven is graded Minor. The skill already says this, but the false-alarm rate shows it isn't binding.
3. **spec:** require the spec to restate every concrete fact from the request and the user's answers (examples, values, expected outputs) verbatim in a "Given" section, before any design content.
4. **spec:** keep the "don't over-ask" guidance prominent. The 20% control-ask rate is the main cost.

## Measurement caveats

- **Small n:** `plan` and `build` have 9 projects each, with repeats. `review.swe` has only 20 broken and 20 correct patches. Several real-looking differences have CIs that include zero.
- **Mutation ceiling:** `test.mutation` saturates at 97.5% for both arms. It needs harder code (for example the HumanEval+ or MBPP+ hard subsets) or stronger mutation operators to discriminate.
- **`test_first` not measured:** the `build.devbench` `test_first` metric is broken. Agents write files through Bash heredocs, which the metric (built for Write/Edit tool calls) doesn't see, so it has data for 1 of 18 skill records.
- **Model judges:** judges and simulated users are `opus`. Every judge rationale and conversation is in `results/full/*/records.jsonl` for spot checks.
- **Usage-limit restarts:** the run was interrupted twice by the account's 5-hour usage limit. Records from those periods were discarded and rerun; the harness now stops on that condition instead of recording it.

Reproduce one task:

```bash
python -m fsevals.cli run plan.devbench --n 9 --reps 3 --arms baseline,skill --out results/full/plan.devbench
```
