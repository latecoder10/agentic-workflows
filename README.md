# agentic-workflows

A registry of reusable, **agent-agnostic** workflows for AI coding agents —
Claude Code, Cursor, OpenCode, Antigravity, Aider, Windsurf, a plain
terminal session with an LLM in the loop, whatever you're using. Nothing
here depends on one vendor's skill/plugin format.

## Why this exists

When an agent works through a non-trivial multi-step task (video processing,
data pipelines, whatever), it re-derives the same approach — and re-learns
the same mistakes — every single time, in every project, regardless of which
agent or model is doing the work. This repo is where that gets captured once
and reused: a workflow here is a folder containing

1. **A plain-language instructions doc** (`README.md`) any agent can read
   and follow, written to explain *why* each step matters, not just *what*
   to do — so an agent with good judgment can adapt it instead of following
   it blindly off a cliff.
2. **Deterministic scripts** that do the actual work (`scripts/`), so the
   agent orchestrates and reasons about content, not about re-deriving
   ffmpeg filter graphs or API request shapes from scratch each time.
3. **A lessons-learned doc** (`references/LESSONS.md` or similar) capturing
   real failure modes that were hit and fixed — this is the highest-value
   part of the registry. Anyone can write "here's how to do X"; the value
   here is "here's how X actually goes wrong and why."

## Using a workflow

Point your agent at a workflow's `README.md` (or `AGENTS.md`, if your tool
auto-loads that convention — see below) and describe your task. Or, if your
tool can read structured data, `registry.json` at the repo root is a
machine-readable index of everything available, with tags and a one-line
summary per workflow, so an agent (or a script) can pick the right one
without reading every README.

```
git clone <this-repo> ~/agentic-workflows
# then, from your project:
# "use the narrated-demo-video workflow at ~/agentic-workflows/workflows/narrated-demo-video
#  to add a voiceover to demo.mp4"
```

### `AGENTS.md`

Several agent tools (and more every month) auto-discover a root-level
`AGENTS.md` and load it as standing context. This repo has one — it's
intentionally short (a pointer, not the full instructions) so cloning this
registry alongside a project doesn't bloat every session's context with
workflows you're not using right now. Each workflow also has its own scoped
`AGENTS.md` for tools that support nested/per-directory instruction files.

## What's in the registry

| Workflow | Summary | Tags |
|---|---|---|
| [`narrated-demo-video`](workflows/narrated-demo-video) | Adds a single continuous, precisely-synced AI voiceover to a silent screen-recording, rebuilding the video's timing to match the narration instead of forcing narration into fixed cues. | video, ffmpeg, elevenlabs, voiceover |

(Also see `registry.json` for the machine-readable version of this table.)

## Adding a workflow

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: if you (human or
agent) just worked through something non-trivial, got it *actually right*
after some trial and error, and it's the kind of thing you'll want again in
a different project — that's a workflow. Extract it while the mistakes are
still fresh; that's most of the value.

## Design principles

- **No vendor lock-in.** A workflow must work with nothing more than "an
  agent that can run shell commands and read text output." Vendor-specific
  conveniences (e.g. a Claude Code Skill wrapper) can *also* exist and point
  back at a workflow here, but the workflow itself doesn't require one.
- **Scripts do deterministic work; the agent does judgment work.** If a step
  has one correct mechanical answer (parsing timestamps, running ffmpeg,
  computing a duration delta), it's a script, not a paragraph of prose
  asking the agent to "carefully calculate." Reserve agent reasoning for
  things that genuinely need it (reading images, writing prose, deciding
  what to do about a scan that comes back ambiguous).
- **Explain why, not just what.** Instructions that only say "always do X"
  fail silently in the 10% of cases where X is wrong for a good reason. Explain
  the reasoning so an agent (which is often smarter than the rigid
  instruction gives it credit for) can actually apply judgment.
- **Capture failure modes, not just the happy path.** A workflow's
  `references/` doc should read like a post-mortem, because that's what it
  is — the "what went wrong and why" is what saves the next run from
  repeating it.
