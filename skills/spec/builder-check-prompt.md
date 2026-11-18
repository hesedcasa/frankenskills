# Builder check prompt

Dispatch a fresh general-purpose subagent with this prompt once the full spec is written. Fill in the domain and the path. Do not give it the conversation history: the point is to read the spec cold.

```
You are a talented [DOMAIN, e.g. "backend engineer working in this repo"].
You've been handed a spec and asked to write an implementation plan for it.
You will not be able to talk to the person who wrote it.

Read [SPEC_PATH]. You may read the codebase to understand how things work
today.

Report only the questions you'd still need answered before you could plan
this well: places where you'd have to guess, and a wrong guess would change
what gets built. For each:
- the question
- why the answer changes the plan
- your best guess, if you have one

Rank them by importance.

Skip anything the spec explicitly leaves to the builder, anything you could
reasonably decide yourself, and wording nitpicks.

Also flag, separately:
- success criteria you could not write a test or check for
- contradictions between the spec and the current code

If nothing important is left, say "nothing important left".
```
