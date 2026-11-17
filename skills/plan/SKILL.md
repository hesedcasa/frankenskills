---
name: plan
description: Use when there is an approved spec or clear requirements for multi-step work and no implementation plan yet, before touching code; when a task feels too big to start; when work must be split across sessions, agents, or PRs; when the implementation order isn't obvious; or when the user says "plan", "break this down", "tasks", "tickets", or "how should we build this". Not for one-file changes with an obvious approach.
---

# Plan

Turn an approved spec into an ordered set of small, independently verifiable tasks, each carrying exactly the decisions an implementer cannot make alone: which files, which names and signatures, which tests prove it, which command shows it passed.

**Core principle:** A plan is the set of decisions the implementer can't make alone. A line that decides nothing is a gap. A function body the signature and tests already determine is a transcript. Both are defects.

**Pipeline position:** `spec` → **`plan`** → `build` (+ `test`) → `review`. Planning is read-only: no product code is written here.

## Step 0: Should this be planned?

- **No approved spec, and the work is non-trivial** → stop and use the `spec` skill first. Don't invent requirements.
- **One or two files, obvious approach** → skip the plan. Say so, list the 2–3 steps inline, and hand to `build`.
- **The spec covers several independent subsystems** → propose one plan per subsystem; each must produce working, testable software on its own.
- **Too big for one agent session to hold** (multi-week, still foggy) → plan only the first stretch you can see clearly, and list the rest under *Not yet planned* with the question that must be answered before it can be.

**Never overwrite an incomplete plan.** If a plan file already exists with unchecked tasks: same work being revised → edit it in place; different work → stop and ask. Those tasks may be mid-build in another session.

## Step 1: Ground in the code (read-only)

- Read the spec in full, including Decisions, Boundaries, Testing decisions, and Out of scope.
- Read the code the change touches and the code next to it. Identify existing patterns, conventions, test locations, and the project's real commands (build, focused test, full suite, typecheck, lint, run the app). Check `package.json`/`Makefile`/`pyproject.toml`/CI config rather than guessing `npm test`.
- Note the data shapes first: core types, how they're accessed, who owns each piece of state. Get the shape right before sequencing logic.
- Look for **prefactoring**: changes that make the feature easy before the feature lands. "Make the change easy, then make the easy change."
- Look for **subtraction**: dead code, obsolete paths, or redundant layers to remove first so you build on a simpler base.

## Step 2: Map files and interfaces

Before writing tasks, list which files will be created or modified and what each is responsible for. This is where decomposition gets locked in.

- One clear responsibility per file; files that change together live together; split by responsibility, not technical layer.
- Follow the codebase's existing structure. Include a split of an unwieldy file only if you'd otherwise pile onto it.
- Name the interfaces that cross task boundaries: exact function/type names, parameters, return types, error modes. These are how a task implementer who sees only their own task learns what neighbors produce.

## Step 3: Slice and order

**Slice vertically.** Each task is a tracer bullet: a narrow but complete path through every layer it needs (schema → API → UI → test), demoable or verifiable on its own. Not "all the DB, then all the API, then all the UI".

**Order by proof, not by importance:**

1. Subtraction and prefactoring first (they land green on their own).
2. Scaffolding everything else needs (shared types, test harness, CI wiring), folded into the first task that needs it.
3. **Riskiest unknown next.** If the risky piece fails, find out before investing in the rest.
4. Then the remaining slices in dependency order.

**Wide refactors are the exception to vertical slicing.** A mechanical change that fans across the codebase (rename a column, retype a shared symbol) is sequenced **expand → migrate → contract**: add the new form beside the old; migrate callers in batches sized by blast radius, each its own task; delete the old form in a final task blocked by every batch.

**Contract-first** when parts must proceed in parallel: one task defines the shared contract (types, API schema); dependents build against it.

**Mark dependencies** on every task (`Blocked by: Task 2, Task 3` or `None`). The **frontier** is every task whose blockers are done. Tasks on the frontier with disjoint files can run in parallel; tasks sharing files, migrations, or mutable state run sequentially.

**Checkpoints** every 2–3 tasks and at every phase boundary: full suite green, build clean, the core flow works end-to-end in the running system, and (optionally) a human look before continuing.

## Step 4: Size each task

A task is the smallest unit that carries its own test cycle and is worth a reviewer's gate on its own. Fold setup, config, and docs into the task whose deliverable needs them; split only where a reviewer could reject one piece while approving its neighbor.

| Size | Files | Example | Verdict |
|---|---|---|---|
| XS | 1 | Add a validation rule | Fold into a neighbor unless it's independently reviewable |
| S | 1–2 | One endpoint or component | Ideal |
| M | 3–5 | One feature slice | Ideal |
| L | 5–8 | Multi-component feature | Split it |
| XL | 8+ | — | Must split |

Split further when the task needs more than one focused session, its acceptance criteria won't fit in three bullets, it touches two independent subsystems, or its title contains "and".

## Step 5: Write the plan

Use [plan-template.md](plan-template.md). Save it beside the spec (`specs/<feature-slug>/PLAN.md`) unless the project has its own convention or tracker. Every task contains:

- **Goal** — one sentence: the end-to-end behavior this task makes work.
- **Files** — create / modify (with line ranges when known) / test.
- **Interfaces** — *Consumes* (exact signatures from earlier tasks) and *Produces* (exact signatures later tasks rely on).
- **Acceptance criteria** — specific, testable, three bullets at most.
- **Steps**, each one action with a checkable result, in RED → GREEN order:
  1. Write the failing test: its name and assertions, with the spec's exact values as literals.
  2. Run it: exact command + the expected failure (and *why* it fails: "function not defined", not "some error").
  3. Implement: exact signature and file; one line on approach only where the signature and test leave a real choice; a code block only for an algorithm they don't determine.
  4. Run it: exact command + expected PASS. Then the task's verification (suite, typecheck, lint, runtime check).
  5. Commit: which files, and the message.
- **Blocked by** and **Size**.

**What a step must not contain:** "TBD", "handle edge cases", "add appropriate validation", "write tests for the above", a type or function no task defines, or a body the signature and tests already determine.

### Global sections

- **Global constraints** — the spec's project-wide requirements, one line each, exact values copied verbatim (version floors, naming rules, perf budgets, allowed dependencies). Every task implicitly includes them.
- **Review focus** — the up-to-five input classes or failure modes the spec implies but no task's tests yet exercise, most likely to bite a real user first (empty input, concurrent edits, unauthorized caller, huge payload, network failure…). For each, add the pinning test to the owning task. The spec's silence on an input is not permission for it to break.
- **Risks and mitigations**, **Parallelization** (frontier groups), **Open questions**.

## Step 6: Self-review

Read the spec again with fresh eyes and check the plan against it. Fix problems inline.

1. **Coverage** — point to the task implementing every spec requirement and success criterion. Add tasks for gaps.
2. **Step scan** — every step lets the implementer write exactly one reasonable thing. Fix placeholders and transcripts.
3. **Type consistency** — names and signatures in later tasks match what earlier tasks produce (`clearLayers()` in Task 3 vs `clearFullLayers()` in Task 7 is a bug).
4. **Review focus** — each line has its test in an owning task. An empty section means you checked and found none.
5. **Proportion** — if the plan is several times longer than the spec, or mostly code blocks, you've written the program. Replace bodies with signatures, test names, and assertions.
6. **Verifiability** — every task ends in a state you can check; no task leaves the build broken (unless it's an explicitly declared expand/migrate step).

For a large or contested plan, also dispatch a fresh-context subagent to read the spec and plan cold and report gaps, contradictions, and wrong ordering.

## Step 7: Hand off

Present the plan path, the task list with dependencies, the parallel groups, and what stays unproven. Ask the user to approve it and choose how to execute:

- **Inline** — you implement every task in this session, then one fresh reviewer checks the whole branch. Cheapest; fine for tightly coupled tasks or a well-specified plan.
- **Subagent per task** — a fresh implementer per task and a fresh reviewer after each, then a whole-branch review. Most thorough; best for long plans and independent tasks.
- **Parallel frontier** — independent tasks run concurrently, each in its own worktree/branch, merged to an integration branch. Fastest; needs disjoint files.

Recommend one in a sentence grounded in the plan (how coupled the tasks are, how many, what a mistake costs). **End your turn.** Execution starts on the user's explicit go, via the `build` skill.

If the project uses an issue tracker for work, publish one ticket per task in dependency order (blockers first) using native blocking links, with the plan file as the index. Never close or rewrite another plan's open tickets.

## Common rationalizations

| Thought | Reality |
|---|---|
| "The tasks are obvious" | Write them down. Explicit tasks expose hidden dependencies and forgotten edge cases. |
| "I'll figure it out as I go" | That's how tangled diffs and rework happen. |
| "I can hold it all in my head" | Context windows end and compaction forgets. The plan survives both. |
| "I'll put the full code in the plan to be safe" | Then the plan is the program, and the review of it is a code review in disguise. Decide names, tests, and values; let the implementer write bodies. |
| "Edge cases: handle appropriately" | That decides nothing. Name the input and the expected behavior, and put the test in a task. |
| "Horizontal layers are cleaner" | Nothing works end-to-end until the last task, so integration bugs surface last. Slice vertically. |
| "The old plan is stale, I'll replace it" | Its unchecked tasks may be mid-build elsewhere. Ask. |

## Red flags

- Writing product code during planning
- A task without a failing test, a run command, or an expected output
- Tasks sized L or XL
- No dependency marks; high-risk work scheduled last
- Interfaces that differ between the producing and consuming task
- Placeholders ("TBD", "as needed", "appropriate") anywhere in a step
- A plan longer than the code it describes
- Starting `build` without the user's go

## Verification

- [ ] Approved spec exists (or the work was small enough to skip it, stated)
- [ ] Real project commands discovered, not assumed
- [ ] File map and cross-task interfaces written before tasks
- [ ] Tasks are vertical slices, S/M sized, ordered subtraction → scaffold → riskiest → rest
- [ ] Every task has acceptance criteria, a named failing test, run commands with expected output, and dependencies
- [ ] Global constraints and Review focus written; review-focus tests assigned
- [ ] Self-review done: coverage, step scan, type consistency, proportion
- [ ] No incomplete plan overwritten
- [ ] Plan presented with an execution recommendation; turn ended for approval
