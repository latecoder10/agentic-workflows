# Lessons learned -- git-timesheet

## `git log --since`/`--until` filters on committer date, not author date, and this broke the tool on first real test

**What happened:** first version of `collect_commits.py` used
`git log --since=X --until=Y` directly. Tested against a real repo
(`document-extraction-service`) known from a manual `git log` histogram to
have 14 commits on 2026-08-17. A single-day query for that exact date
(`--since="2026-08-17 00:00:00" --until="2026-08-17 23:59:59"`) returned
**zero** commits.

**Why:** `--since`/`--until` filter on the *committer* date
(`%cd`), while the script was displaying and grouping by *author* date
(`%ad`). Checked across the repo: 34 of 43 commits (79%) had a committer
date different from their author date -- most were authored across late
July/August but all carry committer dates of 2026-09-01, meaning the
history was rewritten or bulk re-pushed at some point after the fact. Any
date-windowed query using git's native filter would have either dropped
these commits entirely (if the window was narrow) or, worse, silently
placed them on the wrong day if a broader window happened to catch them --
exactly the failure mode a timesheet tool cannot afford, since "which day
was this work done" is the entire point.

This is not a contrived edge case. It's the *normal* case for exactly the
workflow this tool targets: "devs work for days and push after a few
days" (amend, rebase, squash-merge, or cherry-pick onto a clean history)
routinely produces a committer date that reflects when the ref was
updated, not when the work happened.

**Fix:** dropped `--since`/`--until` from the `git log` invocation
entirely. `collect_commits.py` now pulls full commit history (still with
`--author` filtering, which git applies against author identity
correctly) and filters to the requested window in Python by parsing the
author date (`%ad`) explicitly. The committer date is still captured
(`committer_date` field) and a warning is surfaced when it diverges from
author date, purely as visibility -- it never affects placement.

**How to avoid regressing this:** if you're tempted to "optimize" this by
pushing the date filter back into the git command for performance,
don't -- add a coarse `--since` as a pure performance pre-filter only if
profiling actually shows it's needed, and keep the Python-side author-date
filter as the authoritative one regardless. Never let git's native date
window be the only filter.

## Author identity is not one `(name, email)` pair per person

While testing across the four POC repos, the same person appeared as three
distinct identities in one repo alone: `Ayan Pal <aypal@estuate.com>`,
`Ayan Pal <palayan789@gmail.com>`, and `ayan-estuate <ayan.pal@estuate.com>`.
A naive "filter by one email" approach would have silently dropped 2/3 of
that person's real commits. `--author` is repeatable and OR'd by git
natively, which is why the workflow asks the user to confirm every
identity that's theirs (after showing them the distinct list from
`git log --pretty=format:'%an|%ae' | sort -u`) rather than assuming a
single canonical identity.

## Binary files show `-`/`-` in `--numstat`, not `0`/`0`

`git log --numstat` prints literal `-` for insertions/deletions on binary
files (e.g. a `.docx` or `.png` in the diff), not `0`. Parsing that column
with `int()` unconditionally throws. Handled by detecting `-` and
recording `binary: true` with 0/0 rather than crashing the whole collector
over one binary file in an otherwise-normal commit.

## Sanitizing characters is safe to automate; rewriting AI-sounding prose is not

Tested `build_timesheet.py`'s sanitizer against a deliberately bad
description containing markdown (`*robust*`), an em dash, a `#refactor`
hashtag, and stock AI phrasing ("Furthermore, I leveraged..."). Character
stripping worked cleanly and produced valid plain text. Left the AI-tell
detection as a *warning*, not an auto-rewrite -- there's no deterministic
way to turn "Furthermore, I leveraged a robust approach" into something
that reads like a specific human wrote it without understanding what the
commit actually did, which is exactly the judgment call this workflow
reserves for the agent, not the script.
