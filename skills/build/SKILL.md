---
name: build
description: Use when implementing an approved plan or the next task from one; when picking up a ticket to code; when resuming implementation after a break or context compaction; when about to write more than a few dozen lines of production code; or when the user says "build", "implement", "execute the plan", "next task", or "build auto". Not for exploratory spikes the user has labelled throwaway.
---

# Build

Implement a plan one thin, verified slice at a time: failing test, minimal code, green suite, commit, ledger line, next. Leave the system working after every slice and leave a record that survives your own forgetting.

**Core principle:** The plan already did the thinking. Execute it exactly, prove every step with output you actually read, and record every decision you make on the user's behalf.

**Pipeline position:** `spec` → `plan` → **`build`** (drives `test` every task) → `review`.

## Step 0: Preconditions

1. **A plan exists.** Look for the plan beside the spec (`specs/<slug>/PLAN.md`) or wherever the project keeps plans. If there's none and the work is non-trivial, stop and use the `plan` skill. For a genuinely small change (1–2 files, obvious approach), write the 2–5 steps as a todo list and proceed.
2. **The plan was approved.** If it wasn't, present it and wait.
3. **Clean baseline.** `git status --porcelain` shows nothing except the spec/plan files. Uncommitted unrelated work: stop and ask the user to commit, stash, or confirm. Per-task commits must not absorb it.
4. **Isolated branch.** Never implement on `main`/`master` without explicit consent. Use a feature branch, or a git worktree if other work is in flight.
5. **Green start.** Run the full suite and build once. Record the result. Failures that exist before you touch anything are noted in the ledger as pre-existing, not silently inherited.

## Step 1: Set up the ledger

Conversation memory does not survive compaction; an executor that loses its place re-implements finished tasks. Keep a ledger file beside the plan (`specs/<slug>/LEDGER.md`, or a git-ignored path if the project prefers):

```
# Build ledger — plan: specs/export-csv/PLAN.md
Baseline: a1b2c3d — suite 212/212, build ok
Pre-flight: Task 3 consumes toCsv(rows, columns) from Task 2 — matches
Task 1: complete (a1b2c3d..d4e5f6a, tests: pnpm test → 214/214)
Task 2: Ruling: plan says return Buffer, spec says string — used string (spec binds) — cost if wrong: one signature change
Task 2: complete (d4e5f6a..9f8e7d6, tests: pnpm test → 219/219)
```

**On start or resume:** if the ledger exists and names this plan, every `Task N: complete` line is done: don't redo it. Trust the ledger and `git log` over your recollection. Resume at the first task without a completion line.

**Pre-flight scan (before Task 1):** for every task that consumes what an earlier task produces, compare the two Interfaces blocks. Record each pair and any conflict, and rule on conflicts with the spec as the binding authority.

## Step 2: Pick the execution mode

Use what the user chose at the plan handoff. If they didn't choose, recommend one and proceed.

| Mode | When | How |
|---|---|---|
| **Inline** | Coupled tasks, short plan, or no subagent tool | You do every task below yourself. One fresh reviewer for the whole branch at the end. |
| **Subagent per task** | Long plan, mostly independent tasks, high cost of mistakes | Fresh implementer per task using [implementer-brief.md](implementer-brief.md); you review each task's diff (spec compliance + quality) before the next; whole-branch review at the end. Never two implementers on the same files at once. |
| **Parallel frontier** | Many independent tasks with disjoint files | One implementer per frontier task, each in its own worktree/branch based on an integration branch; merge each into the integration branch as it lands; new frontier → new implementers. |

In any mode, **you own the result.** Read every diff a subagent produces; a subagent's "done" is a claim, not evidence.

## Step 3: The task loop

For each task, in dependency order:

### 3.1 Take the task
Re-read the task's text from the plan file now, even if you remember it. You remember a summary; the plan has the exact values, signatures, and test cases. Record `BASE=$(git rev-parse HEAD)`. Mark the todo in progress.

### 3.2 Work the steps, test first
Follow the plan's steps in order under the `test` skill:

1. **RED** — write the failing test the plan names. Run it. Watch it fail **for the expected reason**. A test that passes before the code exists is a finding about the test.
2. **GREEN** — write the minimum code that makes it pass. No speculative options, parameters, or "while I'm here" changes.
3. **Run the focused test** while iterating; the full suite once at the end of the task.
4. **Refactor** only with green tests, and only within the task's files.

Every step with an expected output gets compared against real output. Three outcomes:

- **Matches** → next step.
- **The code is wrong** → debug to the root cause (see "When something fails"). Never patch the symptom or edit the test to match wrong code.
- **The plan is wrong** (contradicts the spec, an interface doesn't match, a command can't work) → make the smallest change that satisfies the spec, write a ruling in the ledger, continue.

### 3.3 Implementation rules

- **Simplest thing that works.** Three similar lines beat a premature abstraction. No generic event bus for one notification, no config-driven builder for three forms. Ask: would a staff engineer say "why didn't you just…"?
- **Data shape first.** Name the types and who owns each piece of state before writing logic. Prefer a state machine over parallel booleans, a typed model over loose parameters, a lookup table over a spreading if/else chain.
- **Scope discipline.** Touch only what the task requires. Don't reformat, re-import, or "clean up" adjacent code. Record what you notice instead:
  ```
  NOTICED, NOT TOUCHING:
  - src/utils/date.ts has an unused import (unrelated)
  ```
- **One logical change per commit.** Refactor, feature, and config change are three commits.
- **Keep it compilable.** After each task the build passes and existing tests pass, unless the plan explicitly declares this an expand/migrate step with scoped breakage.
- **Safe defaults.** New behavior is opt-in or flagged until complete: `const notify = options?.notify ?? false`. Unfinished user-visible features go behind a feature flag.
- **Rollback-friendly.** Additive changes over in-place rewrites; migrations come with a rollback; don't delete and replace in the same commit.
- **Validate at boundaries, trust inside.** Parse external input (HTTP, CLI, files, env) into domain types at the edge. No redundant re-validation inside.
- **Follow the codebase's patterns.** Match naming, error handling, and file layout of neighboring code. A new pattern needs a reason in the ledger.

### 3.4 Completion contract
A task is complete only when all of these are true **with evidence from this session**:

- Every test the task names exists, was seen failing, and now passes. You read the output.
- The full suite passes (or fails only on recorded pre-existing failures).
- Typecheck, lint, and build pass where the project has them.
- For user-visible behavior: you exercised it in the running system (CLI invocation, HTTP request, browser) and observed the expected result.
- Every deviation from the plan has a `Ruling:` line in the ledger.

### 3.5 Commit and record
Stage only the files this task touched (never `git add -A` blindly). Commit with a descriptive message (imperative subject, body says why). In the same step, append to the ledger:

`Task N: complete (<base7>..<head7>, tests: <command> → <result>)`

Mark the todo complete. At a plan checkpoint, run its checks (full suite, build, end-to-end flow) before the next task.

## Rulings, not stalls

Conflicts, ambiguities, and plan defects get decided, not parked. The spec binds, the plan argues, your judgment settles the rest. Record each:

`Task N: Ruling: <what you decided> — <why> — <what it costs if wrong>`

Don't pause between tasks to ask "should I continue?". **Only four things stop you:**

1. An irreversible or destructive operation (data deletion, destructive migration, force-push).
2. A security-sensitive action (auth/permission changes, secrets, payments).
3. A side effect outside the branch that norms say you ask about (merge, push to a shared branch, deploy, publish, messaging people).
4. A plan so broken that every path forward is a guess, or a spec decision the spec doesn't cover and the answer changes what gets built.

For those, stop and ask with the specific decision needed and your recommendation.

## When something fails

- **Reproduce first.** Get the failure to happen on demand. Read the actual error, the actual state, the actual values. Instrument if needed.
- **Fix the root cause**: the first place the system did something it shouldn't. Guards, retries, swallowed errors, and clamped values usually hide bugs. If the state that triggered it should never exist, find what produced it.
- **Fix the pattern, not the instance.** Search for the same fault elsewhere in what you're touching.
- **Two failed fixes sharing a premise → attack the premise.** Write down the one sentence every failed fix assumed, and test it directly before writing another fix.
- **Three attempts without progress → stop and report**: what you tried, what you observed, what you think is wrong, and what would help.

## Finishing

When every task is complete:

1. Run the full suite, typecheck, lint, and build one final time, fresh. Exercise the feature's success criteria from the spec in the running system.
2. Hand off to the `review` skill for a fresh-context whole-branch review. Do not substitute your own reading of your own diff.
3. Fix Critical and Important review findings in one pass, each with a failing test first (via `test`), then a green suite. Record each in the ledger.
4. Report to the user:
   - What was built, task by task, with commit ranges
   - Verification evidence (commands and results)
   - **Rulings I made** — every `Ruling:` line, in order, with cost-if-wrong
   - **Noticed, not touched** and **deferred minor findings**
   - Anything not verified, and why
5. Push, open a PR, or merge only as the user or project norms direct.

## Common rationalizations

| Thought | Reality |
|---|---|
| "I remember what Task N says" | You remember a summary. Re-read it. |
| "I'll test it all at the end" | A bug in slice 1 makes slices 2–5 wrong. Test each slice. |
| "This refactor is small enough to include" | Mixed refactors make both changes harder to review and revert. Separate commit. |
| "The plan's wrong here, I'll just do the right thing" | Do the right thing and ledger the ruling. An unrecorded deviation is a decision made in secret. |
| "Let me check in before the next task" | The user approved the plan. Only the four stops stop you. |
| "The subagent said it's done" | That's a claim. Read the diff and the test output. |
| "It compiles, so it works" | Compiling isn't behavior. Run it. |
| "I'll update the ledger after a few tasks" | Compaction doesn't wait. One line per task, with the commit. |
| "Let me run the suite again to be sure" | Re-running unchanged code adds nothing. Run after the next change. |

## Red flags

- More than ~100 lines written without running a test
- Production code written before its failing test
- A test that passed the first time it ran, accepted without question
- Touching files outside the task "while I'm here"
- `git add -A` with unrelated changes in the tree
- Editing a test so it matches wrong behavior; skipping or disabling a failing test
- Claiming done without fresh command output in this session
- A plan deviation with no ruling in the ledger
- Asking "should I continue?" between tasks

## Verification

- [ ] Clean baseline, isolated branch, baseline suite result recorded
- [ ] Ledger exists, names the plan, has one completion line per finished task
- [ ] Every task: failing test seen, minimal code, focused + full tests green, committed alone
- [ ] Every deviation has a ruling; every out-of-scope observation listed
- [ ] Success criteria exercised in the running system
- [ ] Whole-branch `review` done; Critical/Important fixed test-first
- [ ] Final report lists rulings, deferred items, and anything unverified
