---
name: review
description: Use when a task, feature, or branch is finished and before it is merged; when reviewing a PR, a diff, work-in-progress, or code another agent or model wrote; when asked "what could this break" or "is this safe to merge"; and when receiving review feedback, before acting on it. Also for "review", "code review", "review since <ref>", "check this before I merge", or "stress test this change".
---

# Review

Judge a change on two separate axes, **did it build the right thing** (spec) and **is it built well** (quality), with fresh eyes, findings backed by evidence, and severity graded by what a real user would hit. Then act on findings with technical rigor, not deference.

**Core principle:** Approve a change when it definitely improves the health of the codebase and does what was asked, even if it isn't how you'd have written it. Never approve one you haven't actually read and checked.

**Pipeline position:** `spec` → `plan` → `build` (+ `test`) → **`review`** → merge.

## Step 1: Pin the scope

- The user names the scope (PR, branch, commit range, files). Otherwise: the current branch against its merge-base with the default branch, plus uncommitted changes.
- Resolve the fixed point and confirm the diff is non-empty before doing anything else: `git rev-parse <ref>`, `git diff <ref>...HEAD --stat`, `git log <ref>..HEAD --oneline`. A bad ref or an empty diff fails here.
- For a PR, read its description and linked issues.

## Step 2: Gather the intent

Find, in order: the spec and plan the change implements (`specs/<slug>/`, links in commits/PR, a path the user gave), the build ledger's `Ruling:` lines, and the issue it closes. Restate the intent in two or three sentences. If there's no spec, say so: the spec axis then judges against the PR description and the reasonable expectations of a user.

Also find the standards: `CONTRIBUTING.md`, `CODING_STANDARDS.md`, `CLAUDE.md`/`AGENTS.md`, lint configs, ADRs, the glossary.

**Size check.** ~100 changed lines is ideal, ~300 is fine for one logical change, ~1000 is too big to review well: recommend a split (stack, by file group, or vertical slices) as a finding. Refactoring mixed with feature work is two changes.

## Step 3: Review with fresh context

The author is blind to their own assumptions, and so is the session that wrote the code. When a subagent tool is available, **dispatch reviewers with fresh context** using [reviewer-prompt.md](reviewer-prompt.md): give them the diff (as a file or exact command), the spec/plan paths, the standards files, and the ledger rulings. **Never** your session history. Reviewers are read-only and do not spawn their own reviewers.

Run in parallel, so one axis can't mask the other:

- **Spec reviewer**: missing, extra, misunderstood.
- **Quality reviewer**: correctness, tests, design, security, performance.
- *(Optional, for risky or wide changes)* **Blast-radius reviewer**: what this breaks somewhere grep won't show.

Use the most capable model available for a whole-branch review. Without a subagent tool, do each axis yourself as a separate pass, and label the result a self-review: weaker than a fresh reviewer, and the user decides if that's enough.

Reviewing your own just-finished branch inline is not a substitute for this step.

## The spec axis

Compare the diff to what was asked:

- **Missing**: requirements or success criteria skipped, partial, or claimed but not implemented. Quote the spec line.
- **Extra**: behavior nobody asked for, speculative options, hooks, or abstractions (scope creep, YAGNI).
- **Misunderstood**: right feature built the wrong way, or the wrong problem solved.
- **Unverifiable from the diff**: requirements that live in unchanged code or span changes. List what to check rather than guessing.

**The spec is a vision document, not an exhaustive list.** Where it's silent, a reasonable user's expectation is the requirement. Silence about an input is not permission for it to crash.

## The quality axis

Read the **tests first**: they reveal intent and coverage.

**Tests**
- Does every new behavior have a test that would fail if the behavior broke? Answer by experiment where you can: flip a condition the change adds, run the suite, restore. A mutation that stays green is a finding: name the missing test.
- Behavior through public seams, not internals; no assertions on mocks; no expected values computed by the code under test; mocks only at system boundaries.
- Bug fixes have a regression test. Nothing skipped or disabled. Test output clean.

**Correctness**
- Matches the spec; edge cases (null, empty, zero, max, unicode, concurrent); error paths, not just the happy path; off-by-one, races, state that can get out of sync.

**Readability and simplicity**
- Names say what things are and do. Control flow is straightforward. Could this be fewer lines? Does each abstraction earn its keep (no generalizing before the third use)?
- Dead code, no-op variables, `// removed` comments, compatibility shims nobody needs.
- Comments explain *why*, not *what*. A comment narrating a workaround often marks a root cause left unfixed.

**Design**
- Fits the existing patterns; a new pattern needs a reason.
- Does a refactor **reduce** the concepts a reader must hold, or only move them? Prefer the version where branches, modes, or layers disappear.
- Feature logic leaking into a shared module; a near-duplicate of an existing helper; a conditional bolted onto an unrelated flow; repeated switches on the same shape (a missing model or dispatcher); a second boolean that must stay in sync with the first (a missing state machine).
- One-caller wrappers and pass-through layers (inline them). Mutable state wider than it needs to be.
- Validation at boundaries, trust inside. No silent fallbacks papering over an unclear invariant; no gratuitous `any`/casts.
- File growth: a change that pushes a file far past a healthy size should decompose first.

**Security**
- Untrusted input (HTTP, CLI, files, env, LLM output, third-party responses) validated at the boundary. Queries parameterized. Output encoded. Authn/authz checked where needed. Secrets out of code, logs, and VCS. New dependencies justified, maintained, licensed compatibly; lockfile diff reviewed.

**Performance**
- N+1 queries, unbounded loops or fetches, missing pagination, sync work that blocks, large allocations in hot paths, needless re-renders. Quantify when you can ("~50ms per row at 1k rows").

**Smell baseline** (judgment calls; the repo's documented standards override): Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Repeated Switches, Shotgun Surgery, Divergent Change, Speculative Generality, Message Chains, Middle Man.

## The blast-radius axis (risky or wide changes)

Listing callers is not the job; grep does that in a second. The job is the breakage grep won't show:

- Find **the one fact the change is safe because of** ("this call only drops entries that are already dead"). Prove it by running code: a script that imports the real library at the pinned version and calls the exact function in question.
- Look where symbol search stops: library source and local patches, execution timing (async ordering, teardown), serialized formats (JSON shapes, DB columns, wire protocols, other languages reading the same bytes), feature flags, consumers three hops away.
- For each risk: how it breaks, `file:line`, likelihood, cost, and the cheapest check. List checked-and-cleared risks separately.

## Step 4: Verify every finding

A finding that sounds right is not a finding until checked.

- Check it against the callers, guards, and tests that reach the code. Drop it if they rule it out.
- Prove the important ones: a failing test, a repro script, or command output showing the wrong behavior. Prefer findings proven by a run over plausible ones.
- Label **pre-existing** defects separately from **regressions** this change introduces.
- Merge findings that share a root cause.
- **Zero findings is a valid result.** Don't invent one to look thorough.

## Step 5: Grade and report

Grade by **effect on a reasonable person using the software if it ships**, not by whether the spec mentions the trigger.

| Severity | Meaning | Required action |
|---|---|---|
| **Critical** | Security hole, data loss, broken core functionality | Blocks merge |
| **Important** | Wrong or fragile behavior, missed requirement, untested behavior, swallowed errors, damaging duplication or design | Fix before merge |
| **Minor** | Polish, small simplifications, broader coverage | Author's call; record if deferred |
| **Nit** | Style preference | Optional |
| **FYI** | Context, no action | None |

Lead with leverage: correctness and security first, then structural problems and missed simplifications, then the rest. If there's one structural problem and ten nits, the structural problem *is* the review. **Propose the move, not just the problem**: "replace this if-chain with a lookup keyed by `kind`", "inline this one-caller wrapper", "reuse `formatDate` from `utils/date.ts`".

Be honest: no rubber-stamp "LGTM", no softening a real bug into "might be a minor concern", no inflating nits to Critical. Acknowledge what's done well, specifically.

Use the format in [reviewer-prompt.md](reviewer-prompt.md#output-format): spec verdict, strengths, issues by severity (each with `file:line`, what's wrong, why it matters, how to fix, evidence), blast-radius notes, **declined to judge** (behaviors considered and set aside, with why), and a verdict: **Approve**, **Approve with fixes**, or **Request changes**. Keep the spec and quality sections separate; don't rerank across them.

## Step 6: Act on findings (when you are the author)

Review feedback is input to evaluate, not orders to perform.

1. **Read all of it** before reacting. If any item is unclear, ask about it before implementing *anything*: items are often related.
2. **Restate** each item as a technical requirement, and **verify it against the code**. Is it correct for *this* codebase? Does it break something? Was there a reason for the current code? Does the reviewer have the full context?
3. **Push back with evidence** when it's wrong: a test, a `file:line`, a measurement. If a suggestion adds an unused "proper" feature, check usage; YAGNI applies to reviewers too. Escalate to the user anything that conflicts with their earlier decisions.
4. **Fix in order**: Critical/blocking → simple → complex. Each fix gets a failing test that reproduces the finding first (via `test`), then the fix, then a green full suite. One focused fix pass, not an endless loop.
5. **Minors** you don't fix go in a "Deferred" list in your final message. A finding you decide not to fix is a recorded decision with a reason.
6. **No performative agreement.** No "You're absolutely right!", "Great catch!", or thanks. State what you changed ("Fixed: empty rows now emit a header-only CSV; test `exports header for empty view`") or why the code stands. If you pushed back and were wrong, say so in one line and fix it.

On GitHub, reply in the inline comment thread, not as a top-level comment.

## Before merge (Definition of Done)

- [ ] Every spec success criterion met and verified in the running system
- [ ] New behavior has tests that fail without the change; full suite green, clean output
- [ ] No Critical or Important findings open; deferrals recorded with reasons
- [ ] No dead code, debug output, or commented-out blocks; changes scoped to the task
- [ ] Lint, typecheck, build pass
- [ ] Migrations, config, and flags accounted for; rollback path exists for risky changes
- [ ] Public interfaces and user-visible behavior documented; ADR for hard-to-reverse decisions
- [ ] Commit messages and PR description say what changed and why, in standalone terms
- [ ] The human approved where the project requires it

## Common rationalizations

| Thought | Reality |
|---|---|
| "Tests pass, so it's good" | Tests don't catch wrong design, security holes, or a misread spec. |
| "I wrote it, I know it's right" | Same author, same blind spots. Get fresh eyes. |
| "AI-generated code is probably fine" | It's confident and plausible when wrong. It needs more scrutiny, not less. |
| "The refactor is cleaner" | If the reader holds the same number of concepts, it only moved. |
| "We'll clean it up later" | Later rarely comes. Fix it now or file it explicitly. |
| "The spec didn't mention that input" | Silence isn't permission. Grade by what the user gets. |
| "The reviewer said Minor, so it's Minor" | Re-grade by effect. |
| "The fix is obvious, no test needed" | The failing test is the only proof the finding was real and is now gone. |
| "The reviewer is probably right" | Verify against the code first. |

## Red flags

- "LGTM" with no evidence of reading
- Findings without `file:line`, or claimed without checking callers and guards
- Spec and quality findings merged into one ranked list
- Nits buried above a correctness bug
- A reviewer handed the author's session history
- Fixing review findings without a failing test first
- Implementing some feedback items while others are still unclear
- Performative agreement or thanks instead of a stated fix

## Verification

- [ ] Scope pinned; diff non-empty; intent and standards gathered
- [ ] Spec and quality reviewed separately with fresh context (or self-review declared)
- [ ] Tests reviewed first, with at least one mutation experiment on new logic
- [ ] Every reported finding verified; important ones proven by a run
- [ ] Severity graded by user effect; remedies proposed
- [ ] Verdict given; declined-to-judge list included
- [ ] As author: every item evaluated, fixes test-first, deferrals recorded
