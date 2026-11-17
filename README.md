# frankenskills

Five skills that take a coding agent from a vague request to merged code:

```
  spec ──────▶ plan ──────▶ build ──────▶ review ──▶ merge
  what & why    ordered,      one verified    fresh eyes,
  approved      testable      slice at a      spec + quality,
  by a human    tasks         time            evidence-backed
                                │
                                └── test (every task: red → green → prove it)
```

| Skill | Use when | Output | Gate |
|---|---|---|---|
| [`spec`](skills/spec/SKILL.md) | A request is non-trivial or underspecified | `specs/<slug>/SPEC.md` | Human approves the spec before anything is built |
| [`plan`](skills/plan/SKILL.md) | An approved spec exists and work spans several steps | `specs/<slug>/PLAN.md` | Human approves the plan and picks an execution mode |
| [`build`](skills/build/SKILL.md) | Implementing a plan or its next task | Commits, one per task + `specs/<slug>/LEDGER.md` | Each task's completion contract; only four things stop the run |
| [`test`](skills/test/SKILL.md) | Writing any production code, fixing a bug, or claiming done | Tests that failed first, plus fresh evidence | No code without a failing test; no claim without fresh output |
| [`review`](skills/review/SKILL.md) | A branch or PR is finished, or feedback arrives | Spec and quality findings, graded, with a verdict | No Critical/Important open at merge |

Each skill also works alone: `test` and `review` are useful on any change, and `plan` accepts a spec written elsewhere.

## Install

Claude Code (plugin):

```
/plugin marketplace add hesedcasa/frankenskills
/plugin install frankenskills@frankenskills
```

Or copy individual skills into your agent's skills directory:

```bash
cp -r skills/* ~/.claude/skills/
```

Any agent that reads `SKILL.md` folders (frontmatter `name` + `description`) can use them. Supporting files sit next to each `SKILL.md` and are referenced by relative path.

## Artifacts

By default a feature gets one folder, so the spec, plan, and build record travel together:

```
specs/<feature-slug>/
├── SPEC.md      # spec: what and why, approved
├── PLAN.md      # plan: tasks, interfaces, tests, commands
└── LEDGER.md    # build: completion lines and rulings; survives context compaction
```

If a project already has conventions (OpenSpec, `docs/specs/`, an issue tracker), the skills follow those instead.

## Design choices

Where the four source collections disagree, these skills pick one side:

- **Questions in `spec`** — one at a time by default with a recommended answer attached (interview-me, superpowers), but up to three independent questions may go together when they sit on the same frontier of the design tree (Matt Pocock's grilling). Facts are looked up, never asked.
- **Execution in `build`** — no check-ins between tasks. Decisions are recorded as rulings in a ledger (superpowers), and only four kinds of action stop the run (irreversible, security-sensitive, outward-facing, or a plan so broken every path is a guess). That's closer to pstack's "never block on the human" than to addy's stop-after-each-task default.
- **TDD strictness in `test`** — the iron law holds (superpowers), with a short list of exceptions that must be stated out loud. When a failing test would be impractical, the fallback is the closest executable check, never no check at all (pstack).
- **Review structure** — spec and quality are separate axes reviewed in parallel by fresh-context agents and never reranked together (Matt Pocock). Inside quality, addy's five axes, Fowler's smells, and pstack's blast-radius pass. Severity reflects what a real user would hit (superpowers), and findings need evidence, ideally a run (pstack interrogate).
- **Plans decide, they don't transcribe** — signatures, test names with literal assertions, commands, and expected output. Function bodies appear only for algorithms the tests don't determine (superpowers).

## Sources and credits

These skills are a synthesis, not a copy. Each one draws on the following MIT-licensed work:

| Skill | Main sources |
|---|---|
| `spec` | addyosmani `spec-driven-development`, `interview-me`, `idea-refine`; mattpocock `to-spec`, `grilling`, `domain-modeling`; pstack `sharpen`, `architect`, `principle-experience-first`; superpowers `brainstorming` (builder check) |
| `plan` | addyosmani `planning-and-task-breakdown`; mattpocock `to-tickets`, `wayfinder`; pstack `multi-phase-plan`, `principle-sequence-verifiable-units`, `principle-foundational-thinking`, `principle-subtract-before-you-add`; superpowers `writing-plans` |
| `build` | addyosmani `incremental-implementation`, `/build`; mattpocock `implement`, `implement-spec`; pstack `feature` playbook, `swarm`, `principle-fix-root-causes`, `principle-attack-the-premise`, `principle-never-block-on-the-human`; superpowers `executing-plans`, `subagent-driven-development` |
| `test` | addyosmani `test-driven-development`; mattpocock `tdd` (seams, tautological tests, mocking); pstack `tdd`, `principle-test-behavior-not-implementation`, `principle-prove-it-works`, `create-verification-skill`; superpowers `test-driven-development`, `writing-good-tests`, `verification-before-completion` |
| `review` | addyosmani `code-review-and-quality`, `definition-of-done`; mattpocock `code-review`; pstack `blast-radius`, `interrogate`, `principle-minimize-reader-load`; superpowers `requesting-code-review`, `receiving-code-review`, task reviewer |

- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — Copyright (c) 2025 Addy Osmani, MIT
- [mattpocock/skills](https://github.com/mattpocock/skills) — Copyright (c) 2026 Matt Pocock, MIT
- [cursor/plugins (pstack)](https://github.com/cursor/plugins/tree/main/pstack) — Copyright (c) 2026 Lauren Tan, MIT
- [obra/superpowers](https://github.com/obra/superpowers) — Copyright (c) 2025 Jesse Vincent, MIT

## License

MIT. See [LICENSE](LICENSE).
