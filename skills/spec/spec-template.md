# Spec template

Copy the block below. For a **small change**, keep every heading but write one or two lines under each and drop sections marked *(full only)*. For a **project**, fill everything.

```markdown
# Spec: <Feature name>

Status: draft | approved | implemented
Owner: <who approves>
Date: YYYY-MM-DD
Supersedes / extends: <link to original spec if this is a delta spec, else omit>

## Problem
<The problem, from the user's perspective. Who has it, when, and what it costs them today.>

## Given
<Every concrete fact from the request, the code, and the user's answers, copied verbatim: examples, exact inputs and expected outputs, error messages, versions, reproduction steps. Nothing paraphrased, nothing dropped.>

## Outcome
<What will be true when this ships, in one or two sentences. Why now.>

## Users and stories  (full only)
1. As a <actor>, I want <capability>, so that <benefit>
2. ...
<Be extensive: cover every actor and every path, including error and empty states.>

## Success criteria
<Specific, testable conditions. Each one can be checked by a test, a command, or an observation of the running system.>
- [ ] <e.g. A signed-in user can export the current view as CSV in under 3s for 10k rows>
- [ ] <e.g. Exports exclude rows the user cannot see in the UI>
- [ ] Must NOT change: <existing behavior that has to keep working>

## Non-goals and anti-goals
- Non-goal: <reasonable thing we're deliberately not doing>
- Anti-goal: <outcome that would make this a failure even if it technically works>

## Constraints
<Binding limits with exact values: platforms, versions, budgets, latency targets, compliance, dependencies allowed.>

## Approaches considered
| Approach | Trade-off | Verdict |
|---|---|---|
| A: <name> | <what it costs / buys> | **Chosen**: <why> |
| B: <name> | <...> | Rejected: <why> |

## Decisions
<What was decided, one bullet each. Mark who decided.>
- [user] <decision>
- [agent call] <decision> — <reason>
Includes, as relevant: modules built or modified, their interfaces, data shapes / schema changes, API contracts, state machines, error behavior.
<No file paths or code, unless a spike produced a snippet (schema, type, reducer) that states a decision more precisely than prose. Mark it "from spike".>

## Testing decisions
- Seams: <the public interfaces at which behavior is observed; prefer existing and highest-level>
- What a good test looks like here: <behavior through the seam, not internals>
- Prior art: <similar tests in the codebase to follow>
- Beyond unit tests: <how the running system will be exercised to prove the success criteria>

## Boundaries
- Always: <e.g. run the full suite before commit; follow existing naming>
- Ask first: <e.g. schema migrations, new dependencies, CI changes>
- Never: <e.g. commit secrets, edit vendored code, disable failing tests>

## Left to the builder
<Choices the plan/implementer may make freely.>

## Out of scope (deferred)
- <idea> — <why deferred>

## Open questions
- <anything unresolved; empty when approved>
```

## Delta spec (change to a shipped feature)

```markdown
# Delta spec: <change name>

Status: draft | approved | implemented
Original spec: <link>

## Current behavior
<What exists today, with a pointer to the original spec section.>

## Change
<What changes, and why.>

## After
<What will be true after the change.>

## Success criteria
<Testable, including what must NOT change.>

## Boundary deltas
<Only deltas from the original's boundaries; everything else inherits.>
```
