# Implementer brief (subagent-per-task and parallel-frontier modes)

Use this when dispatching a fresh subagent to implement one task. The subagent gets only what it needs: never your session history, never the whole plan.

**Before dispatching:**
- Record `BASE=$(git rev-parse HEAD)`.
- Extract the task's full text from the plan into its own file (e.g. `specs/<slug>/tasks/task-N.md`). Exact values live only in that file.
- Pick a report path (`specs/<slug>/tasks/task-N-report.md`).
- Choose the model deliberately: cheapest capable tier for mechanical tasks whose plan pins every signature and test; standard tier for multi-file integration; most capable for design judgment. An omitted model inherits the session's (often most expensive) one.

```
You are implementing Task N: <task title>, part of <one line on the feature>.

## Requirements
Read this first: <TASK_FILE>. It is your requirements, with the exact values,
signatures, and tests to use verbatim.
Global constraints that bind this task: <paste the plan's Global constraints>
Interfaces from earlier tasks you consume: <exact signatures, or "none">
Decisions already made that the task file can't know: <rulings from the ledger
that touch this task, or "none">

## Work from
<repo path / worktree path>, branch <branch>, based on <BASE>.
Commands: focused test `<cmd>`, full suite `<cmd>`, typecheck `<cmd>`.

## Before you begin
If anything about the requirements, approach, or dependencies is unclear,
ask now, before writing code.

## Your job
1. Write the failing test the task names. Run it. Confirm it fails for the
   expected reason, and keep that output.
2. Write the minimal code to pass it. Nothing the task didn't ask for.
3. Run the focused test while iterating.
4. Self-review your diff (below) and fix what you find.
5. Run the full suite, then commit only this task's files with a descriptive
   message. Any later fix gets its own commit: the review covers BASE..HEAD,
   so uncommitted work is invisible to it.
6. Write your report and reply.

## Rules
- Touch only what the task requires. Note anything else under "Noticed, not
  touched" in your report instead of fixing it.
- Follow the patterns of neighboring code.
- Never edit a test to match wrong behavior. Never skip or disable a test.
- Do not dispatch subagents of any kind, including reviewers. Review happens
  after you report.
- If a file you're creating grows well beyond the task's intent, stop and
  report DONE_WITH_CONCERNS rather than restructuring on your own.

## Stop and escalate (BLOCKED or NEEDS_CONTEXT) when
- The task needs an architectural decision with several valid answers
- You need code or context you can't find after a focused search
- You're unsure your approach is correct
- You've tried three fixes for the same failure
Bad work is worse than no work. Escalating is never penalized.

## Self-review before reporting
- Did I implement every acceptance criterion? Anything extra?
- Do the tests assert observable behavior with independently known expected
  values, not mock calls or values recomputed by the code under test?
- Would each test fail if the behavior broke?
- Are names accurate? Is the test output free of warnings?

## Report
Write the full report to <REPORT_FILE>:
- What you implemented; files changed
- RED evidence: command + failing output + why that failure was expected
- GREEN evidence: command + passing output; full-suite result
- Self-review findings; noticed-not-touched; concerns

Then reply in under 15 lines:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- Commits (short SHA + subject)
- One-line test summary (e.g. "14/14 passing, output clean")
- Concerns, if any
- Report path
```

## Handling the report

- **DONE** → read the diff (`git diff <BASE>..HEAD`) and the report. Review the task for **spec compliance** (missing / extra / misunderstood) and **quality** using the `review` skill's task-scoped checklist. Clean → ledger line, next task. Findings → resume the same implementer with the findings; it fixes them test-first and appends a fix report. Cap at three rounds, then rule on what remains and ledger it.
- **DONE_WITH_CONCERNS** → read the concerns before reviewing; decide whether each is a finding.
- **NEEDS_CONTEXT** → supply the missing context and resume.
- **BLOCKED** → split the task, give more context, re-dispatch on a more capable model, or rule. Never let a blocked task silently become "done".
