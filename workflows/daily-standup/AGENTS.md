# AGENTS.md -- daily-standup

Full instructions: [`README.md`](README.md). Read it before running
anything here -- the short version is:

1. **Ask the user conversationally in plain text** for inputs if not already
   provided:
   - Any other repo paths besides the current directory.
   - Any external blockers they want to report today (defaults to "None" if
     they have none; never invent blockers).
   - Author identity / name only if ambiguous (or pass `--all-authors` for
     solo repos).
2. **Run `scripts/collect_activity.py`** to collect recent commits, active
   branches, working copy diffs, stashes, and unpushed commits into
   `activity.json` (deterministic).
   - Note: on Mondays, it automatically looks back to Friday 00:00:00 to
     prevent the weekend amnesia trap.
3. **Write `standup.json` yourself** -- this is the step that requires judgment:
   - Group messy or "wip" commits into clear, feature-level achievements for
     `yesterday`.
   - Inspect `working_tree` (staged/unstaged diffs) and `stashes` to ground
     what is actively planned for `today`.
   - Keep bullets under 25 words each, concise, direct, and free of AI buzzwords
     (no "spearheaded", "orchestrated", "delved", "seamless").
4. **Run `scripts/verify_standup.py`** to validate brevity, check for banned AI
   clichés and raw commit hashes, and render the final standup to Markdown,
   Slack mrkdwn, or plain text. Revise if warnings or errors are surfaced.

Critical gotchas (see `references/LESSONS.md`):
- "Today" is in the working tree and stashes, not in yesterday's git log.
- Never invent blockers; if there are no external impediments, state "None."
