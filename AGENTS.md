# AGENTS.md

This repository is a **registry of agent-agnostic workflows** — see
[`README.md`](README.md) for the full explanation. If you're an AI coding
agent operating in or alongside this repo:

- `registry.json` is a machine-readable index of every workflow available
  here (id, summary, tags, path to its full instructions).
- Each workflow lives at `workflows/<id>/` with its own `README.md` (full
  instructions) and `AGENTS.md` (short pointer, for tools that auto-load
  nested instruction files). Read a workflow's own docs before using it —
  don't rely on the one-line summary in `registry.json` alone.
- If you (or the user) just worked through a non-trivial multi-step task
  outside this repo and it went well after some iteration, consider whether
  it belongs here as a new workflow — see `CONTRIBUTING.md`. The best time
  to extract it is right after getting it right, while the mistakes that
  were made along the way are still fresh enough to document.
