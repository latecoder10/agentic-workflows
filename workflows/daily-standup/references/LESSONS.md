# Lessons learned -- daily-standup

## 1. The "Monday Standup" Amnesia Trap

**What happened:** On a Monday morning test run, querying git for "yesterday's activity"
returned zero commits across every repository. A naive agent following this output
summarized: *"Yesterday: No recorded activity. Today: Continuing previous tasks. Blockers: None."*

**Why:** Calendar arithmetic is not business calendar arithmetic. Sunday is "yesterday"
on Monday. Since software engineers rarely commit on Sundays (and if they do, it's sporadic),
a simple 1-day lookback drops Friday's entire day of work — the exact work the engineer
actually needs to report in Monday's morning standup.

**Fix:** `collect_activity.py` checks `datetime.date.today().weekday()`. If `weekday() == 0`
(Monday) and no custom `--since` is provided, the lookback window automatically expands
to 3 days prior (Friday 00:00:00). It sets `is_monday_lookback: true` in the output metadata
so the agent understands why Friday's commits are included in the lookback window.

## 2. "Today" cannot be found in git log — it lives in the working tree and stashes

**What happened:** Initial prompts asking an agent to produce a standup purely from git
commits produced either pure hallucinations for the "Today" section (*"Today I will coordinate
with backend engineers to optimize architecture"*), or simply repeated yesterday's commits verbatim.

**Why:** Pushed commits are historical facts about the past. What a developer is doing
*today* is almost never a pushed commit yet; it is represented by:
1. The currently checked-out branch (e.g. `feat/webhook-retry`).
2. Uncommitted staged/unstaged changes in the working tree (`git status --porcelain`, `git diff --stat`).
3. Recent stashes (`git stash list`), which commonly capture in-flight work paused at the end of the previous day.
4. Unpushed local commits ahead of upstream (`git log @{u}..HEAD`).

**Fix:** `collect_activity.py` inspects both commit history and local working tree state.
If `working_tree.unstaged_files` shows edits in `src/webhooks/metrics.py` on branch
`feat/webhook-retry`, the agent has concrete, diff-grounded evidence to write:
*"Today: Adding metrics collection to webhook retry worker and finishing test coverage."*

## 3. The AI Aggrandizement Trap & Standup Etiquette

**What happened:** Given a commit `fix: align header padding with navbar`, an LLM generated:
> *"Spearheaded a comprehensive UX refinement by meticulously optimizing frontend container
> padding to enhance user engagement and ensure robust layout harmony."*

In an actual 15-minute engineering standup or async Slack thread, this kind of puffed-up
prose sounds fake, wastes teammates' time, and damages credibility. Engineers want:
> *"Aligned header padding with navbar across dashboard views."*

**Why:** Standard LLM system prompts bias toward verbose, impressive-sounding descriptions.
Without hard mechanical guardrails, agents turn routine 10-line bugfixes into corporate press releases.

**Fix:** `verify_standup.py` enforces mechanical boundaries:
- Word limits: warns if any single bullet exceeds 25 words; rejects if it exceeds 40 words.
- Section limit: recommends at most 4 bullets per section (standups are not sprint retrospectives).
- Cliché detection: flags banned AI filler words (`spearhead`, `orchestrate`, `delve`, `seamless`, `robust`, `leverage`, `meticulously`, `streamline`).
- Format: strips raw 40-character commit hashes (e.g. `7a3f8c2`), requiring human-readable component names instead.

## 4. "WIP" commit churn vs meaningful progress

**What happened:** A developer working on a complex feature made five commits in a day:
`wip`, `checkpoint 2`, `fix lint`, `more tests`, `wip again`. A naive script mapped each commit
directly to a bullet point, producing five nearly identical, meaningless bullets.

**Why:** Git commit granularity varies wildly between developers and workflows. Some developers
squash before pushing; others commit every 20 minutes locally.

**Fix:** The workflow explicitly tasks the agent with synthesizing commits by touched module
or feature branch. `collect_activity.py` aggregates `top_components_touched` and file numstats
to give the agent the necessary high-level view.

## 5. Hallucinating Blockers vs Genuine Blockers

**What happened:** When no blockers were mentioned, an agent invented one:
*"Blocker: Need to thoroughly test edge cases in asynchronous execution."*

**Why:** Writing code or testing edge cases is regular engineering work, not a blocker.
A blocker is an external impediment outside the developer's immediate control:
- Blocked by a pending pull request review from another team.
- Waiting on API credentials or third-party service provisioning.
- Blocked by a broken staging environment or test infrastructure outage.

**Fix:** The workflow rule states: If the user did not declare an external blocker and no
hard blockers exist in the collected data, the "Blockers" section must simply state `"None."`
or `"No blockers."` Agents are forbidden from inventing internal task complexity as blockers.

## 6. Windows Terminal Encoding (`cp1252` / `cp437`)

**What happened:** When running `verify_standup.py --format slack` or printing bullet characters
(`•`) on Windows PowerShell/CMD, Python raised `UnicodeEncodeError: 'charmap' codec can't encode character '\u2022'`.

**Why:** Windows default console standard output encoding is often a legacy OEM code page
(such as `cp437` or `cp1252`) rather than UTF-8.

**Fix:** Both `collect_activity.py` and `verify_standup.py` include explicit UTF-8 reconfiguration
for Windows consoles (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`).
