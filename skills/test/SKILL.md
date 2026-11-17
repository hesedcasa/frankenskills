---
name: test
description: Use when writing or changing any production code (feature, bug fix, refactor, behavior change), before writing the implementation; when fixing a bug, before touching the code; when writing, changing, or judging tests or mocks; when deciding where tests should go; and before claiming anything is done, fixed, or passing. Also for "TDD", "red-green-refactor", "write tests for", "prove it works", or "add a regression test".
---

# Test

Tests are proof. Write the failing test first, watch it fail for the right reason, write the least code that makes it pass, and never claim something works without fresh output that shows it.

**Core principle:** If you didn't watch the test fail, you don't know it tests anything. If you didn't run the check in this session, you don't know it passes.

**Pipeline position:** `spec` names the seams → `plan` names the tests → `build` runs this skill every task → `review` judges the tests.

## The two iron laws

```
1. NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
2. NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

Wrote code before the test? Delete it and start from the test. Don't keep it "as reference" and don't adapt it: tests written to fit existing code verify what it does, not what it should do. Exploration is fine; throw it away, then start with the test.

**Allowed exceptions** (say which one you're using, out loud): throwaway spikes the user approved, generated code, pure configuration, and docs. A bug whose failing test is genuinely impractical gets the closest executable check instead (see Bug fixes). "Too simple to test" is not an exception.

## Step 1: Discover how this repo tests

Before the first test, find out, don't assume:

- Language, build system, and test framework (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle`, `Makefile`)
- Checked-in wrappers (`./gradlew`, `make test`, repo scripts) over global tools
- **Focused** command (one file or test) and **full-suite** command; CI config shows what actually gates merges
- Where tests live, how they're named, what the neighboring tests look like (fixtures, factories, test DB, fakes)
- Typecheck and lint commands

## Step 2: Agree the seams

A **seam** is the public interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

- Prefer existing seams, and the highest one that still gives fast, deterministic feedback. Fewer seams across the codebase is better.
- If the spec or plan named the seams, use them. Otherwise propose them, each with one line on what it catches and what it misses, and confirm with the user when the choice is non-obvious.
- If testing a behavior requires reaching past the interface, the module is probably the wrong shape. Say so.

## Step 3: Red → Green → Refactor, one slice at a time

Work **vertically**: one test, then the code for it, then the next test. Never write a batch of tests up front: bulk tests encode imagined behavior and commit you to a structure before you've learned anything.

### RED: write one failing test
- One behavior. Name says what, not how: `rejects empty email`, not `test validate`.
- **Name the break first**: which realistic production change should make this test fail? If you can't name one, you're about to write a test that can't fail.
- Expected values come from an independent source: a literal, a worked example, the spec. Never recompute them the way the code does.

### Verify RED (mandatory)
Run the focused command. Confirm:
- It **fails** (an assertion), it doesn't **error** (import error, typo, missing fixture).
- The failure message is the one you expected, because the feature is missing.

Passes immediately? You're testing existing behavior, or the test is wrong. Fix the test. Errors? Fix the error and rerun until it fails correctly.

### GREEN: minimal code
The simplest code that passes. No extra options, parameters, or features the test doesn't demand.

### Verify GREEN (mandatory)
Run the focused test: passes. Then run the **project's full suite**, not just your file. Output must be clean: no new warnings or noise. Any failure, including one you didn't cause, gets named in your report. A red test that scrolled past unmentioned is a falsified report.

Fails? Fix the **code**, not the test.

### REFACTOR
Only with everything green. Remove duplication, improve names, extract helpers, within the files you're working in. Rerun after each step. Don't add behavior.

Then the next test.

## What a good test is

Judge every test against **two imagined edits**:

1. **Break the behavior** (wrong value, skipped or doubled side effect). Does the test fail? If not, it proves nothing.
2. **Change the internals** while keeping every observable result. Does the test still pass? If not, it's pinned to the implementation.

Keep tests that catch edit 1 and survive edit 2. Rewrite or delete the rest.

| Do | Don't |
|---|---|
| Drive through the public interface with a concrete input | Test private methods or internal call order |
| Assert outcomes callers can observe: return values, errors, readable state, effects on external systems | Assert that an internal collaborator was called |
| Verify through the interface (`create` then `get`) | Verify through a side channel (query the DB the API wraps) |
| Hand-derived literal expected values; table tests with literal `want` | `expected = sameBuilder(input)` (tautology: always passes) |
| Test behavior that depends on a decision ("6th retry never happens") | Change detectors (`expect(MAX_RETRIES).toBe(5)`, exact message wording) |
| Assert the error *type* callers branch on | Assert the error message prose |
| One concept per test; Arrange–Act–Assert | One test that validates five things |
| DAMP: each test readable on its own, even if repetitive | Shared helpers that hide what the test checks |
| Pair "this never happens" with a case where it does | Only happy paths |
| Test your contract with the framework | Test that the framework works |

### Mocks

Preference order: **real implementation → fake (in-memory DB) → stub (canned data) → mock (interaction check)**.

- Mock only at **system boundaries**: external APIs, email/payments, time, randomness, sometimes the filesystem or DB. Never mock your own modules or internal collaborators.
- Learn every side effect of the real thing before replacing it; mock the slow/external level *below* what the test depends on.
- Mock responses mirror the **complete** real structure, not just the fields this test reads.
- **The mock earns no assertions.** Asserting a mock was rendered/called proves only that the mock exists. Assert the real component's behavior.
- If mock setup is more than half the test, switch to an integration test with real components.
- Test-only cleanup lives in test utilities, never as a method on a production class.
- Design for it: inject boundary dependencies; prefer specific functions per external operation (`api.getUser(id)`) over one generic `fetch(endpoint, opts)`.

### Levels

```
E2E (few):          critical user journeys through the real app
Integration (some): real components across a boundary (API + test DB)
Unit (most):        pure logic, no I/O, milliseconds each
```

Pure logic → unit. Crosses a boundary → integration. Critical user flow → one E2E. Crash/rollback behavior → exercise the real boundary: an injected exception isn't process death, and a mocked transaction isn't a rollback.

## Bug fixes: the Prove-It pattern

Don't start by fixing. Start by reproducing.

1. Understand intended vs. actual behavior and the smallest observable reproduction.
2. Write the narrowest test at an existing seam that would have caught it.
3. Run it: it **fails**, and the failure shows the bug. (Fails for another reason → fix the test first.)
4. Fix the root cause with the smallest change.
5. Run it: passes. Run the full suite.
6. For extra confidence: revert the fix, confirm the test fails again, restore.

**If a failing test is genuinely impractical** (needs production-only state, a huge harness, brittle mocks, timing you can't control), use the closest executable check instead: a repro script, a CLI invocation, a browser automation, a log assertion. Say why. **Prefer no new test over a bad test**, but never "no check at all."

Flaky bug? Make the test deterministic (control time, seed randomness, wait on conditions rather than sleeping) and document the signal being locked down.

## Prove it in the real system

Passing unit tests are not proof the feature works. For anything a user or caller can observe, also exercise it for real, and climb this ladder as far as it's cheap:

1. **You said so.** Worthless alone.
2. **You pointed at the line.** A real `file:line`.
3. **You showed the bad case can't be reached.** Walked it step by step.
4. **You ran it.** A test or script calling the real code that fails loudly if you're wrong.
5. **You reproduced it in the running app.** Started the app, drove the feature like a user (CLI, `curl`, browser automation), captured the evidence (output, response, screenshot, row written).

Verify side effects (files, rows, messages) alongside what's visible. When something passes too easily, suspect the observation method before the system. A dry-run or test mode: confirm what it actually skips, don't trust its name.

## Mutation check

Before calling tests sufficient, mutate the production code (mentally, or for real and then restore): wrong constant, flipped condition (`&&`↔`||`, drop a `!`), wrong branch, missing side effect, empty/default return, missing validation for zero/empty/nil/unauthorized/malformed input. At least one test should fail for each realistic mutation. A mutation nothing catches marks an unprotected behavior: add the test.

## Verification before completion

Before **any** claim that something is done, fixed, passing, or working, including "should work now" and "looks good":

```
1. IDENTIFY  which command proves the claim
2. RUN       it, fresh and complete, in this session
3. READ      the full output: exit code, counts, failures, warnings
4. COMPARE   does it actually confirm the claim?
5. THEN      state the claim with the evidence, or state the real status
```

| Claim | Requires | Not enough |
|---|---|---|
| Tests pass | Suite output, 0 failures | An earlier run; "should pass" |
| Build succeeds | Build exit 0 | Lint passing |
| Bug fixed | Original symptom reproduced, now gone | Code changed |
| Regression test works | Seen red, then green | Passes once |
| Feature works | Exercised in the running system | Unit tests green |
| Subagent finished | Its diff and output, read by you | Its "success" message |
| Requirements met | Each criterion checked line by line | Tests green |

A verdict is **verified**, **not verified**, or **inconclusive**. Inconclusive is not a pass. Report negatives.

Don't rerun an unchanged command for reassurance; rerun after the next change.

## Reporting evidence

```
RED:   pnpm vitest run src/export/csv.test.ts
       ✗ quotes fields containing commas — expected 'name\r\n"a,b"\r\n', got undefined
       (expected: toCsv not implemented)
GREEN: pnpm vitest run src/export/csv.test.ts → 6/6 passed
SUITE: pnpm test → 219/219 passed, no warnings
LIVE:  curl -s localhost:3000/export?view=7 | head -2 → header + first row as expected
```

If you couldn't show failing-before evidence, say why and what you used instead.

## Common rationalizations

| Thought | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. The test takes a minute. |
| "I'll write the tests after" | Tests written after pass immediately, which proves nothing. They test what you built, not what you should have built. |
| "I already tested it manually" | No record, not repeatable, misses edge cases under pressure. |
| "Deleting this code is wasteful" | Sunk cost. Unverified code is the waste. |
| "Need to explore first" | Fine. Throw the exploration away, then test first. |
| "This test is hard to write" | Hard to test means hard to use. Fix the design. |
| "I have to mock everything" | The code is too coupled. Inject the boundaries. |
| "The suite was green earlier" | Earlier isn't now. Run it. |
| "That failure isn't mine" | Name it in the report anyway. |
| "I'll just skip this flaky test" | Never skip or disable to go green. Fix it or report it. |

## Red flags (stop and start over from the test)

- Production code before its test, or a test that passed on its first run unquestioned
- Can't explain why the test failed
- Asserting on a mock, or an expected value computed by the code under test
- Tests that break on a refactor that kept behavior
- `npm test` assumed without checking the repo
- "Should", "probably", "seems to", or "Done!" before running anything
- A skipped, disabled, or weakened assertion to make the suite pass
- Trusting a subagent's "all tests pass" without its output

## Verification

- [ ] Repo's real focused and full-suite commands used
- [ ] Every new behavior has a test at an agreed seam
- [ ] Each test was seen failing for the expected reason before the code existed
- [ ] Minimal code to green; full suite green with clean output
- [ ] Tests survive the two imagined edits; no tautologies, no mock assertions
- [ ] Bug fixes have a reproduction that failed before and passes after
- [ ] Mutation check run; gaps filled
- [ ] User-visible behavior exercised in the running system
- [ ] Every claim backed by output from this session
