# daily-standup

Reconstructs an accurate, concise 3-part daily standup update (**Yesterday**,
**Today**, **Blockers**) from local git activity across one or more repositories.
It grounds "Yesterday" in actual author commits, discovers "Today" from active
branches, working tree diffs, and stashes, and prevents common LLM failure
modes (weekend amnesia, corporate puffery, and invented blockers).

## When to use this

Use this workflow whenever the user asks:
- "Prepare my daily standup update."
- "What did I work on yesterday and what's on my plate today?"
- "Generate a quick Slack update for my team standup."
- "Summarize my git activity across these repos for standup."

This workflow is not for multi-week billing timesheets (use [`git-timesheet`](../git-timesheet)
for that) -- it is specifically designed for the daily developer standup ritual
where brevity, grounding, and team credibility matter.

## Why this is harder than "run git log and print it"

1. **The Monday Lookback Trap.** If you run a standup on Monday morning, a
   naive 1-day lookback queries Sunday (finding 0 commits). On Monday, the
   lookback window must start from Friday 00:00:00 through the weekend.
   Otherwise, the engineer appears to have accomplished nothing on Friday.
2. **"Today" cannot be found in git log.** Pushed commits represent past
   history. What a developer is doing *today* lives in their local working tree:
   the checked-out branch, uncommitted staged/unstaged changes, and recent
   stashes (`git stash`). Naive agents without working tree inspection either
   invent tasks out of thin air or duplicate yesterday's completed work.
3. **Commit churn vs. meaningful progress.** Real developers make commits like
   `"wip"`, `"checkpoint"`, `"fix typo"`, or squash multiple iterations.
   Listing every commit hash makes a terrible standup update; synthesizing
   feature-level progress requires agent judgment.
4. **The AI Aggrandizement Trap.** Without hard constraints, LLMs turn a
   10-line CSS fix into *"Spearheaded a comprehensive UX paradigm shift by
   meticulously optimizing container margins to foster robust cross-functional
   harmony."* In a real standup, teammates immediately detect AI fluff.
   Standups need crisp, factual bullets under 25 words each.
5. **Invented Blockers.** LLMs often feel compelled to fill every section and
   invent blockers out of routine engineering work (*"Blocker: Need to write unit
   tests"*). A blocker is strictly an external impediment; if none exist, it
   must say `"None."`

## Design: scripts do the mechanical parts, the agent does the writing

```
collect_activity.py  -->  [agent writes standup.json]  -->  verify_standup.py
  (commits, branch,             (the judgment step:            (enforce brevity,
   diffs, stashes)            synthesizing progress)          ban AI filler, render)
```

- `scripts/collect_activity.py` deterministically collects git data across
  multiple repos, handles Monday calendar math, extracts diff stats, and checks
  working copy status.
- **You (the agent)** apply judgment to summarize features, group commits,
  and write plain, human bullets.
- `scripts/verify_standup.py` deterministically enforces word count limits,
  flags banned AI buzzwords and raw commit hashes, and formats the output for
  Markdown or Slack.

## Prerequisites

- `git` on PATH.
- Python 3.8+ on PATH (uses standard library only; no external pip dependencies).

## Step-by-step

### 0. Ask the user for any missing inputs

Ask conversationally in plain text (not option chips or multi-choice menus):

1. **Repositories:** *"Which repositories should I check? (Hit Enter or reply '.' if just the current repo)."*
2. **Blockers:** *"Do you have any external blockers or dependencies today? (Reply 'none' if clear)."*
3. **Author Identity (only if ambiguous):** If the repo has multiple contributors
   and the local git config is unclear, ask which author name or email belongs to them.

### 1. Collect activity data

Run `collect_activity.py` pointing to the target repo(s):

```bash
python workflows/daily-standup/scripts/collect_activity.py \
  --repo /path/to/backend-repo \
  --repo /path/to/frontend-repo \
  --out activity.json
```

Key flags:
- `--repo <path>`: Repeatable for multi-repo work. Defaults to current directory (`.`).
- `--author <name/email>`: Filter commits by author identity (repeatable). Auto-detected from `git config` if omitted.
- `--all-authors`: Include all commits regardless of author (useful for solo repositories).
- `--since <YYYY-MM-DD>` / `--until <YYYY-MM-DD>`: Explicit date window override.
- `--days <N>`: Lookback N days prior to `--until`.

On Mondays, `collect_activity.py` automatically sets the lookback to start on
Friday 00:00:00 and marks `"is_monday_lookback": true` in the output JSON.

### 2. Synthesize and write `standup.json`

Read `activity.json` and write `standup.json`. Adhere strictly to these writing rules:

- **Yesterday:**
  - 1 to 3 bullets summarizing what was completed.
  - Group related commits by component or feature branch (do not list raw commit subjects or SHAs).
  - Use past tense action verbs (*"Built"*, *"Fixed"*, *"Implemented"*, *"Refactored"*).
- **Today:**
  - 1 to 3 bullets summarizing active and planned work.
  - Ground this in the `working_tree` (unstaged/staged modified files) and `stashes` from `activity.json`.
  - Use present participle or action verbs (*"Wire"*, *"Complete"*, *"Investigate"*).
- **Blockers:**
  - If the user reported a blocker, write it concisely.
  - If no blockers exist, write `["None."]`. Never invent internal engineering tasks as blockers.
- **Tone & Length:**
  - Maximum 25 words per bullet (ideally 12-18 words).
  - No AI jargon: never use *spearhead*, *orchestrate*, *delve*, *seamless*, *robust*, *leverage*, *holistic*, *pivotal*, *meticulously*, or *streamline*.
  - No raw commit hashes.

Example `standup.json`:

```json
{
  "date": "2026-09-22",
  "author": "Alex Rivera",
  "yesterday": [
    "Core API: Built exponential backoff queue and idempotency handling for webhook dispatch.",
    "Added unit tests covering webhook replay and duplicate payload prevention."
  ],
  "today": [
    "Core API: Wire retry metrics to Prometheus and finalize integration tests.",
    "Dashboard: Fix webhook delivery status badge rendering bug in frontend."
  ],
  "blockers": [
    "Waiting on DevOps for test staging webhook endpoint credentials."
  ]
}
```

### 3. Verify and render the standup

Run `verify_standup.py` to validate constraints and render to your preferred format:

```bash
# Render to Markdown
python workflows/daily-standup/scripts/verify_standup.py standup.json \
  --activity activity.json \
  --format markdown \
  --out standup.md

# Render to Slack / Teams mrkdwn
python workflows/daily-standup/scripts/verify_standup.py standup.json \
  --format slack
```

Supported formats:
- `markdown`: Clean GitHub-flavored markdown with headers (`## Standup`, `### Yesterday`).
- `slack`: Slack/Teams format with bold titles (`*Yesterday:*`) and bullet characters (`•`).
- `plain`: Indented text format (`YESTERDAY:`, `TODAY:`).

If `verify_standup.py` reports any warnings (e.g. verbose bullets, detected buzzwords),
revise `standup.json` and re-run before presenting the output to the user.
