# Contributing a workflow

A workflow belongs here if it's a **non-trivial, multi-step task** you (or
an agent you were driving) figured out well enough to want to reuse — in a
different project, possibly with a different agent tool entirely. One-off
tasks and things with a single obvious correct approach don't need this;
the value here is capturing hard-won structure and failure modes for things
that *aren't* obvious.

## Structure

```
workflows/<your-workflow-id>/
├── README.md       (required) - full instructions: when to use it, why each
│                                 step matters, exact commands to run
├── AGENTS.md        (recommended) - short pointer to README.md, for agent
│                                 tools that auto-load nested instruction files
├── scripts/         (if applicable) - deterministic code for the parts of
│                                 the workflow that have one correct
│                                 mechanical answer
├── references/      (recommended) - lessons-learned / failure-modes doc(s)
└── examples/         (if applicable) - illustrative input/output, clearly
                                 marked as illustrative, not defaults to reuse
```

Use an existing workflow (e.g. `workflows/narrated-demo-video/`) as a
concrete template rather than starting from a blank page.

## Writing the README

- **Explain why, not just what.** "Always do X" instructions fail silently
  when X is wrong for a reason the instruction didn't anticipate. Explain
  the reasoning behind a step and a capable agent can apply judgment when
  the situation doesn't match exactly.
- **Push mechanical work into scripts.** If a step is "parse this, compute
  that, run this exact command," write the script — don't leave an agent to
  re-derive a filter graph or an API payload shape from a paragraph of
  prose every single time this workflow runs. Scripts should print
  something short and structured (JSON is good) on success, not silently
  succeed or dump megabytes of raw tool output.
- **Keep agent-vendor specifics out of the main instructions.** "Spawn a
  subagent" is a Claude Code-ism; phrase it as "if your agent framework
  supports delegating to an isolated context, use that for step N" so the
  workflow reads correctly regardless of which tool is running it.
- **Don't ship task-specific content as defaults.** If your workflow
  produces a document/script/config as an output, its *content* is
  presumably specific to whatever task you built it for. Keep that out of
  the workflow itself, or clearly mark it as an illustrative example in
  `examples/`, not something to reuse verbatim.

## Writing the lessons-learned doc

This is usually the most valuable file in a workflow. Write it like a
post-mortem: what actually went wrong on a real run, why, and what the fix
was — not a generic list of "best practices" someone could've written
without ever running the thing. If you didn't hit any real failures
building the workflow, you probably haven't tested it enough yet.

## Registering it

Add an entry to `registry.json` at the repo root:

```json
{
  "id": "your-workflow-id",
  "name": "Human-Readable Name",
  "summary": "One sentence: what it does and the key thing that makes it non-obvious.",
  "path": "workflows/your-workflow-id",
  "entry": "workflows/your-workflow-id/README.md",
  "tags": ["relevant", "search", "tags"],
  "requires": ["whatever-tools-or-accounts-it-needs"],
  "agentAgnostic": true,
  "addedBy": "whichever-agent-or-person-built-it",
  "status": "verified | draft",
  "verification": "One sentence on how you confirmed it actually works, ideally with a concrete number (not just \"tested it\")."
}
```

Also add a row to the table in the root `README.md`.

Use `"status": "draft"` if the workflow hasn't been run end-to-end
successfully yet — don't mark something `"verified"` on the strength of it
looking right; run it.

## Removing or superseding a workflow

If you find a better approach to something already in the registry, prefer
updating the existing workflow's README/scripts over adding a parallel one,
unless the old approach is genuinely still useful for different
circumstances (note the distinction in both workflows' READMEs if so).
