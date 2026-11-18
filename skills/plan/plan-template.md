# Plan template

````markdown
# <Feature name> — Implementation Plan

Spec: <path to the approved spec; executors read both>
Status: draft | approved | in progress | done
Execution: inline | subagent-per-task | parallel-frontier

**Goal:** <one sentence>
**Approach:** <2–3 sentences on the shape of the solution>
**Stack and commands:**
- Focused test: `<e.g. pnpm vitest run path/to/file.test.ts>`
- Full suite: `<e.g. pnpm test>`
- Typecheck / lint: `<...>`
- Build: `<...>`
- Run the app: `<...>`

## Global constraints
<Verbatim from the spec, one line each, exact values. Every task includes these.>
- <e.g. Node >= 20; no new runtime dependencies>
- <e.g. Error codes follow `E_<DOMAIN>_<REASON>`>

## File map
| File | Responsibility | Tasks |
|---|---|---|
| `src/export/csv.ts` (new) | Serialize rows to RFC 4180 CSV | 2 |
| `src/api/routes/export.ts` (new) | HTTP endpoint, auth, streaming | 3 |

## Review focus
<Up to five inputs or failure modes the spec implies but no test exercises yet. Each has a test in an owning task.>
1. <Rows containing commas, quotes, newlines → quoted correctly> — Task 2
2. <User without access to a row → row excluded> — Task 3

## Dependency graph
```
Task 1 (prefactor) ──► Task 2 ──► Task 3 ──► Checkpoint A ──► Task 4
                                   └──────► Task 5 (parallel with 4)
```

---

### Task 1: <Short title>

**Goal:** <end-to-end behavior this task makes work>
**Blocked by:** None | Task N
**Size:** S | M

**Files:**
- Create: `exact/path/new_file.ts`
- Modify: `exact/path/existing.ts:120-145`
- Test: `exact/path/new_file.test.ts`

**Interfaces:**
- Consumes: <exact signatures from earlier tasks, or "none">
- Produces: `toCsv(rows: Row[], columns: Column[]): string`

**Acceptance criteria:**
- [ ] <specific, testable>
- [ ] <specific, testable>

- [ ] **Step 1: Write the failing test**
```ts
test('quotes fields containing commas', () => {
  expect(toCsv([{ name: 'a,b' }], [{ key: 'name' }])).toBe('name\r\n"a,b"\r\n');
});
```
- [ ] **Step 2: Run it, confirm it fails**
  Run: `<focused test command>`
  Expected: FAIL — `toCsv is not defined`
- [ ] **Step 3: Implement `toCsv(rows, columns): string` in `src/export/csv.ts`**
  <one line on approach only if the test and signature leave a choice>
- [ ] **Step 4: Run it, confirm it passes; run task verification**
  Run: `<focused test>` → PASS
  Run: `<typecheck>` → 0 errors
- [ ] **Step 5: Commit**
  `git add src/export/csv.ts src/export/csv.test.ts && git commit -m "feat(export): serialize rows to CSV"`

### Checkpoint A (after Tasks 1–3)
- [ ] Full suite green: `<command>`
- [ ] Build clean: `<command>`
- [ ] Core flow works in the running app: <concrete scenario + what you should observe>

---

## Risks and mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| <e.g. 1M-row export exhausts memory> | High | Stream rows (Task 3); test with a 100k fixture |

## Parallelization
- Group 1 (sequential): Tasks 1 → 2 → 3
- Group 2 (parallel after Checkpoint A, disjoint files): Tasks 4, 5

## Not yet planned
<Foggy work you can see coming but can't specify yet, and the question that unblocks it.>

## Open questions
<Empty when approved.>
````
