# AGENTS.md -- git-timesheet

Full instructions: [`README.md`](README.md). Read it before running
anything here -- the short version is:

1. Ask the user, as a plain-text chain in this order -- date range, then
   leave days (if any), then repo folder path(s), then the output folder
   for the finished Excel file. Plain conversational questions, not
   multiple-choice/option-chip UI -- these are exact custom values
   (dates, paths), so just ask and let them type the answer. Author
   identity and hours/day are lighter follow-ups, only if ambiguous (see
   README.md step 0) -- don't pad the main chain with them.
2. Run `scripts/collect_commits.py`, `scripts/plan_calendar.py`,
   `scripts/merge_timeline.py` in that order (all deterministic).
3. Read the merged timeline and write `rows.json` yourself -- this is the
   one step that needs judgment: filling gap days between sparse commits
   with a believable, evidence-grounded narrative, in plain humanized
   sentences (no markdown, no AI-sounding phrasing).
4. Run `scripts/build_timesheet.py` to render and sanitize the output;
   fix and re-run if it reports warnings.

Critical gotcha (see `references/LESSONS.md`): never filter git history by
`--since`/`--until` for this purpose -- that filters on committer date,
not author date, and silently misplaces rebased/re-pushed commits.
`collect_commits.py` already handles this correctly; don't "simplify" it
back to native `--since`/`--until`.
