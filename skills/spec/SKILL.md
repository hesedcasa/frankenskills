---
name: spec
description: Use when starting a new feature, project, or significant change and no approved spec exists yet; when a request is underspecified ("build me X" with no who, why, or definition of done); when requirements are vague, conflicting, or only exist as an idea; when changing a feature that already has a shipped spec; or when the user says "spec", "write a spec", "PRD", "grill me", "interview me", or "stress-test this idea". Not for typo fixes, one-line changes, or requests whose every decision is already stated.
---

# Spec

Find out what the user actually wants and why, settle every decision that would change what gets built, and write it down as a short document that a capable builder could plan from without coming back to ask. Nothing gets built until the user approves it.

**Core principle:** A spec exists to surface misunderstandings while they are cheap. Every assumption you don't say out loud is one the user never got the chance to reject.

**Pipeline position:** `spec` → `plan` → `build` (+ `test`) → `review`. This skill's only output is an approved spec. It never writes product code.

## Step 0: What do you actually know?

Before replying, size the request honestly:

| What you know | What you do |
|---|---|
| Everything that matters is in the request ("make the button blue"; a function signature with a precise docstring and consistent examples; a bug report with exact repro and expected result) | Not a spec job. **Ask nothing.** Do it, or hand straight to `plan`/`build`. Say so in one line. |
| One or two decisions are open, the change is small | **Short spec**: settle them, write a 10–30 line spec, get approval. |
| Something non-trivial is missing, or it touches several modules, or it's a one-way door | **Full spec**: the whole process below. |
| The request bundles several independently testable capabilities | **Capability map first** (Step 1b), then a spec per module. |
| A shipped spec already describes this feature | **Delta spec** (see "Changing something that already has a spec"). |

If the user hasn't asked for a spec conversation and the ask is smallish, offer the exit in one line: *"Or if you'd rather I just dive in, say so."* If they take it, state any significant how-it-gets-made choice in one line and proceed through the normal workflow.

## Step 1: Look before you ask

Finding **facts** is your job. Making **decisions** is the user's.

- Read whatever they pointed at (issues, docs, earlier conversation) and the code it connects to. Keep reading until you can explain how the relevant parts work today and what the change would touch.
- Read `GLOSSARY.md`/`CONTEXT.md`, ADRs (`docs/adr/`), `CLAUDE.md`/`AGENTS.md`, `CONTRIBUTING.md`, existing `SPEC*.md` or `specs/` if they exist. Use the project's vocabulary.
- If a fact needs a wider search (another repo, third-party API docs), dispatch a fresh-context subagent to fetch it. Don't block on it: only questions downstream of that fact wait.
- **Never ask what the project already answers, and never reopen what the user already decided.**

### Step 1b: Scope check (only when the request bundles capabilities)

Decompose before specifying when the requirement names distinct capabilities with their own consumers or data, when acceptance criteria cluster into groups that could ship separately, or when one capability could be cut without rewriting the others. Propose a capability map and get it approved before writing any module spec:

```markdown
| Module id     | Responsibility             | Depends on        |
|---------------|----------------------------|-------------------|
| identity      | Accounts, sessions, SSO    | —                 |
| billing       | Plans, invoices, payments  | identity          |
| notifications | Email and webhook fan-out  | identity          |
Build order: identity → billing, notifications
```

Stable kebab-case ids, dependencies point one way (a cycle means it's one module), contracts live in the provider's spec. Then run this skill once per module in build order.

## Step 2: Hypothesize, then ask

Open with your current read, so the user can correct it fast:

```
HERE'S MY READ: <one sentence: what they want, for whom, why>
CONFIDENCE: ~40% — missing: who uses it, what "fast" means, what's out of scope
ASSUMPTIONS I'M MAKING (correct any now):
1. <assumption grounded in what you read>
2. ...
```

Then work the **design tree**. Every decision branches into the decisions that hang off it. The **frontier** is the set of decisions whose prerequisites are settled.

- **Ask only questions whose answer would change what gets built** and that neither the request nor the project answers. Everything else, state as a proposal with your reason and move on.
- **Don't over-ask.** If you can predict the answer with high confidence from the request, its examples, or the code, don't ask: state it as an assumption. A complete request gets zero questions. Asking about what is already clear costs the user time and signals you didn't read it.
- **Ask the frontier, not the whole tree.** Usually one question per message; up to three when they are genuinely independent. A question that depends on another still-open question waits for a later round.
- **Attach your recommended answer to every question**, with the reasoning, worded so "yes" accepts it. Reacting is faster than generating, and it exposes *your* assumptions. Occasionally recommend something you expect them to push back on.
- **Until you know *why* they want it, ask open questions with no options attached.** Their own words carry intent your options can't. Once you know why, sketch named options concretely, with trade-offs and your pick.
- **Ask Socratically.** Build each question on their last answer or on something you found, so it surfaces a consequence or case they missed: *"Voting closes before the meeting, and two members joined this month. Does someone who joins mid-round get a vote?"*
- **Sharpen fuzzy language.** "Account: do you mean the Customer or the User? Your code treats them differently." When a term is resolved and the project keeps a glossary, update it right then.
- **Cross-check claims against code.** "You said partial cancellation is allowed, but `Order.cancel()` cancels the whole order. Which is right?"

Format:

```
Q: <one focused question>
➡️ RECOMMEND: <your answer + the reasoning that produced it>
(WHY I'M ASKING: <what the answer changes about what gets built>)
```

### Listen for "want" vs. "should want"

Watch for answers that sound like a thoughtful answer instead of a real one: "scalable", "clean", "modern", "the standard way", "I should probably…". Probe once with: *"If you didn't have to justify this to anyone, what would you actually want?"*

### Ground to cover (territory, not a script; never read it out as a questionnaire)

- What it is, who it serves, why now, what success looks like to them
- Goals, **non-goals**, and **anti-goals** (what would make this a failure even if it technically works)
- Current state, what they've tried, prior art they loved or hated
- Binding constraints: deadline, budget, platform, compliance, performance targets
- The details they care about

### Turn vague requirements into testable criteria

```
REQUIREMENT: "Make the dashboard faster"
PROPOSED SUCCESS CRITERIA:
- Dashboard LCP < 2.5s on a throttled 4G profile
- Initial data request completes in < 500ms at p95
- No layout shift during load (CLS < 0.1)
→ Are these the right targets?
```

### Settle it by experiment when you can

If a fork can be settled by running something (does the library support X? how slow is the naive query? what does the layout feel like?), spike it instead of asking. Spikes are throwaway: no tests, not kept. Bring what the spike taught you back into the conversation. Leave product and preference calls, which no experiment settles, to the user.

### When to stop asking

Stop when you can predict the user's reaction to the next three questions you'd ask, and the frontier is empty: every branch visited, nothing silently assumed. If several rounds pass and your confidence isn't rising, stop and say so: *"I've asked N questions and still can't predict your answers. Something foundational is missing. Want to step back?"*

## Step 3: Play it back

Before writing the document, restate intent in the user's words so they can correct it line by line:

```
Here's what I now think you want:
- Outcome:      <one line>
- User:         <who benefits>
- Why now:      <what changed>
- Success:      <how we'll know it worked>
- Constraint:   <the binding limit>
- Out of scope: <what we're explicitly not doing>
Yes / no / refine?
```

"Out of scope" is mandatory: half of misalignment is silent disagreement about what is *not* being built.

**The gate is an explicit yes.** "Whatever you think" is delegation: re-ask as a choice between two concrete options. "Sounds good" is ambiguous: ask "Anything you'd refine?"

## Step 4: Lay out the approaches

In a message of its own, before writing the spec, put the ways of building it side by side:

- Generate several real alternatives, then drop any that work against *why* they want it or that the existing code rules out.
- Sketch the remaining two or three concretely enough to picture: data shape, module boundaries, what changes where. Prefer the shape where each piece of state has one owner, each task has one way to do it, and callers need to know least.
- State each one's trade-off, recommend one, and say why.
- If there is genuinely one sensible way, say so and explain why the others don't fit.
- If the user talks only about outcomes, they're handing you the *how*: make the call, and record it in the spec as your call, not as something they agreed to.

## Step 5: Write the spec

Use the template in [spec-template.md](spec-template.md). Rules:

- **Where it goes:** follow the project's convention if one exists (OpenSpec, `docs/specs/`, an issue tracker). Otherwise `specs/<feature-slug>/SPEC.md`. The plan will live beside it.
- **Size it to the work.** A small change gets the short form (a line or two per section). A project gets the full form. A two-line spec still needs acceptance criteria.
- **Start with "Given": the facts as stated.** Before any design content, copy every concrete fact from the request, the code you read, and the user's answers. Copy them verbatim: examples, values, inputs and expected outputs, error messages, versions, reproduction steps. A spec that loses a stated detail is wrong, however well structured it is.
- **Decisions, not code.** Name modules, interfaces, data shapes, and contracts. Avoid file paths and code snippets: they go stale. Exception: a snippet from a spike that encodes a decision more precisely than prose (a state machine, a schema, a type).
- **Name the test seams.** Where will behavior be observed? Prefer existing seams, and the highest one possible; the fewer seams, the better.
- **Mark what's theirs vs. yours.** Decisions the user made, decisions you made (with reasons), and what's explicitly left to the builder.
- **Out of scope (deferred)** captures every idea cut from this version, one line each with why. Ideas don't get silently dropped or silently included.

### Builder check (full specs)

Dispatch a fresh-context subagent with [builder-check-prompt.md](builder-check-prompt.md). It reads the spec cold as the engineer who must plan from it and lists the questions it would still need answered. Sort each one:

- **Already answered** by the conversation or code → write the answer into the spec.
- **Minor** (a sensible builder could settle it without changing what gets built) → settle it, mark it as your call.
- **Theirs** (only the user can answer, and the answer changes what gets built) → bring these to the user in one message, most important first.

Without a subagent tool, read the spec yourself as that builder, as a separate pass, and say it was a self-check.

## Step 6: Stop for approval (hard gate)

1. Save the spec. Summarize it in a few lines, list your calls and any open questions, and link the file.
2. Ask the user to approve or request changes.
3. **End your turn.** Do not start planning, scaffold, install dependencies, or write code in the same turn.

When approved: set `Status: approved` in the spec, commit it if the project commits docs, and hand off to the `plan` skill. Nothing else.

<HARD-GATE>
Nothing gets built until the user approves the spec. Building includes product code, scaffolding, installing dependencies, creating projects, and invoking `plan`/`build`. Reading, exploring, and approved throwaway spikes are fine. Keeping what a spike produced is a new request that comes back through this gate.
</HARD-GATE>

## Changing something that already has a spec

A shipped spec describes what exists. Don't edit it to describe a change. Write a **delta spec** beside it (`SPEC-<change-slug>.md`) covering only: what exists today (with a link), what changes, what will be true after, success criteria including what must *not* change, and boundary deltas. Run it through this same gate. After it ships, fold the outcome into the original spec and mark the delta `Status: implemented`.

Mid-build scope growth goes to **Out of scope (deferred)**, never straight into the current spec.

## Non-interactive contexts

This skill needs a live user. In CI, scheduled runs, or unattended loops, don't simulate the user's answers. Write the spec with every assumption marked `ASSUMED:` and every open decision under Open Questions, and report the spec as unapproved.

## Common rationalizations

| Thought | Reality |
|---|---|
| "This is simple, no spec needed" | Simple work needs a *short* spec, not no spec. It still needs acceptance criteria. |
| "I'll fill in sensible defaults" | Good. Say them out loud. A default they never heard is one they couldn't reject. |
| "I'll give them a menu of options" | Before you know *why*, options steer. Get them describing first. |
| "Asking questions wastes their time" | Four targeted questions cost minutes. Building the wrong thing costs days, and they pay it. |
| "I'll figure it out while building" | Discovery during implementation is rework. |
| "They said 'sounds good'" | Approval covers what you showed them. A spec you haven't written isn't approved. |
| "I'll write the spec after I code it" | That's documentation. A spec's value is forcing clarity *before* code. |
| "I'll just fold this new idea into the spec" | Mid-build scope growth is how V1 slips. Defer it explicitly. |
| "I'll decompose during planning" | Module boundaries must exist before the spec, or every task reasons over the whole contract. |

## Red flags

- Writing code, scaffolding, or a plan in the same turn the spec was written
- Questions without your recommended answer attached
- Asking the user something you could have looked up
- Batching dependent questions together, or more than three questions in one message
- Accepting "scalable" / "clean" / "robust" as a goal without a number or behavior behind it
- A spec with no Out of Scope section, or success criteria that can't be tested
- Treating your own defaults as decisions the user made
- Three rounds with no visible rise in confidence

## Verification

- [ ] Request was sized; full process used only when warranted
- [ ] Relevant code and docs read before the first question
- [ ] Every assumption stated out loud; every question carried a recommendation
- [ ] Intent played back (Outcome / User / Why now / Success / Constraint / Out of scope) and confirmed with an explicit yes
- [ ] Approaches presented with trade-offs before the spec was written
- [ ] Success criteria are specific and testable; test seams named
- [ ] Out of scope (deferred) captured; user's decisions and your calls marked separately
- [ ] Builder check run (full spec) and its questions triaged
- [ ] Spec saved; turn ended; approval received in a later turn before `plan`
