# git-timesheet

Reconstructs a day-by-day timesheet for a real person from git commit
history across one or more local repos, for a date range the user gives
you. It fills in the days between commits (developers commonly code for
several days and push once), writes plain-language descriptions grounded
in what the commits actually touched, and excludes declared leave days.

## When to use this

The user asks you to "generate a timesheet from my commits," "fill in my
hours for last week based on git history," "reconstruct what I worked on
between date X and date Y," or similar. It is not for estimating time
spent (git history doesn't record duration) -- it's for reconstructing
*what was worked on, on which day*, at a target hours/day, so someone can
fill in a timesheet without staring at `git log` themselves.

## Why this is harder than "run git log and print it"

1. **Commits cluster, days don't.** A person might work Monday through
   Wednesday on one feature and push a single commit Wednesday evening.
   `git log` shows one entry; the timesheet needs three. Deciding how to
   spread one commit's worth of evidence across several real calendar days
   -- and writing a believable progression ("started X" / "kept working on
   X, hit a snag" / "finished X") -- needs judgment, not just date math.
2. **`git log --since/--until` filters on the wrong date for this job.**
   It filters by *committer* date, not *author* date. Any rebased,
   amended, or re-pushed commit gets silently misplaced or dropped from a
   date-windowed query. This is common, not an edge case -- see
   `references/LESSONS.md`. The tooling here filters by author date
   explicitly so "when the work happened" and "when it landed" don't get
   confused.
3. **The output has to read like a human wrote it under time pressure**,
   not like an LLM summarized a diff. That means no markdown artifacts, no
   stock AI phrasing, varied sentence shapes, and text grounded only in
   what the commits actually show -- never invented meetings or details.
   The character-level sanitization is scripted (deterministic); avoiding
   AI-sounding prose is the agent's job and gets flagged, not silently
   fixed, if it slips through.

## Design: scripts do the mechanical parts, the agent does the writing

```
collect_commits.py  -->  plan_calendar.py  -->  merge_timeline.py  -->  [agent writes rows.json]  -->  build_timesheet.py
   (git data)             (date arithmetic)      (gap detection)          (the judgment step)          (render + sanitize)
```

Everything before "agent writes rows.json" has exactly one correct answer
per input and is scripted. The one step that needs a human-like write-up
-- turning "this gap day sits 2 days before a commit that touched 84 files
in the analytics module" into a sentence a person would actually write --
is left to you, the agent, because it's the part that isn't mechanical.

## Prerequisites

- `git` on PATH, and the repos you're scanning are real local git
  checkouts (not shallow clones missing the history you need).
- Python 3.8+ on PATH, with `openpyxl` installed (`pip install openpyxl`).
  If `openpyxl` isn't available, `build_timesheet.py` still writes the
  `.csv` -- only the `.xlsx` step is skipped (it fails loudly with a clear
  error naming the missing package; don't work around it silently).

## Step-by-step

### 0. Ask the user for the inputs -- don't guess them, and ask in plain text

This information lives only in the user's head, so it has to come from
them, not from a guess or a default. Ask as a short **chain of plain
conversational questions, in this exact order, one at a time** -- not as
multiple-choice/option-chip UI (e.g. don't offer canned date-range presets
like "last 7 days"). The answers here are exact custom values (specific
dates, specific folder paths), and forcing them through preset options is
friction, not a shortcut -- just ask and let them type the real answer.

1. **"What date range should this timesheet cover? Give me the start date
   and the end date."** -- this is the period the whole workflow runs
   over. Wait for an actual start/end date, not a vague answer.
2. **"Did you take any leave or days off during that period? If yes, give
   me the exact dates."** -- a plain "no" is a complete answer; if yes,
   collect every date so `plan_calendar.py --leave` gets all of them.
3. **"Did you work across multiple projects during this period? If yes,
   give me the folder path for each repo."** -- if they say just one
   project, get that single repo's path. If multiple, get every path --
   these all feed `--repo` on `collect_commits.py`.
4. **"Where should I save the finished timesheet Excel file? Give me the
   output folder path."** -- don't default this to this workflow's own
   `output/` folder without asking; the user may want it somewhere
   specific (a shared drive, a project folder, wherever they actually
   look for their timesheet).

After that core chain, still resolve two more things, but treat them as
lighter follow-ups rather than part of the main chain -- ask only if
genuinely ambiguous, don't pad the chain with them by default:

- **Author identity**: run
  `git log --pretty=format:'%an|%ae' <repo> | sort -u` per repo first. If
  there's exactly one identity, or the repo is clearly single-author,
  don't bother asking. If there are several distinct `(name, email)`
  pairs, show them the list and ask which ones are theirs (the same
  person is very often multiple identities across repos -- different
  machines, a work vs. personal email, a rename) -- don't just assume the
  first one.
- **Target hours per working day**: default to 8 without asking, unless
  something about the request suggests otherwise (e.g. they mention
  part-time or half-days).
- **Whether weekends count**: default to excluding Saturday/Sunday. Only
  raise it as a question if `merge_timeline.py`'s output shows commits
  actually landing on a weekend in range -- that's a real signal worth
  surfacing, not a routine question to ask up front.

### 1. Collect commit data

```
python scripts/collect_commits.py \
  --repo /path/to/repo-a --repo /path/to/repo-b \
  --since 2026-08-04 --until 2026-08-17 \
  --author "Jane Doe" --author "jane@personal-email.com" \
  --out commits.json
```

Repeat `--repo` for each repo in scope, `--author` for each known identity
(they're OR'd together, matched as git author-pattern regexes). Omit
`--author` entirely to include everyone -- useful for a solo repo. The
script automatically widens the query by `--lookback-days` /
`--lookahead-days` (default 7 each) beyond `--since`/`--until` so gap-day
neighbor lookups near the edges of the range have real commits to point
to, not a cliff.

Check `commits.json`'s top-level `warnings` array before moving on --
it flags repos that weren't valid git repos (skipped, not fatal) and,
per repo, how many commits had a committer date that diverged from their
author date (informational -- author date was already used correctly, but
worth knowing if it's a large fraction, e.g. this repo's history was bulk
re-pushed at some point).

### 2. Build the calendar

```
python scripts/plan_calendar.py \
  --since 2026-08-04 --until 2026-08-17 \
  --leave 2026-08-11 \
  --out calendar.json
```

Repeat `--leave` per leave day. Add `--include-weekends` if the user told
you Saturday/Sunday should default to Working instead of Weekend. This is
pure date arithmetic -- don't hand-count weekdays yourself, and don't let
an agent's own date math substitute for this script's output even though
the answer looks obvious; off-by-one errors here silently corrupt every
downstream step.

### 3. Merge commits onto the calendar and find gap neighbors

```
python scripts/merge_timeline.py \
  --calendar calendar.json --commits commits.json \
  --out merged.json
```

For every non-Leave day, this tells you whether commits landed that day
and, if not, the nearest commit day before and after (with the distance
in days and a summary of what that neighboring commit touched: subject,
file paths, insertion/deletion counts). Read `merged.json` fully before
the next step -- it's the only evidence you have.

### 4. Write the timesheet rows (this is the step that needs you)

Build a `rows.json` shaped like:

```json
{
  "author": "Jane Doe",
  "period_start": "2026-08-04",
  "period_end": "2026-08-17",
  "rows": [
    {"date": "2026-08-04", "weekday": "Tuesday", "project": "repo-a",
     "status": "Working", "hours": 8,
     "description": "Got the new ingest pipeline scaffolded and wired the first Postgres migration in."}
  ]
}
```

One row per date, per project touched that date (a day split across two
repos becomes two rows whose hours sum to the target). Leave and Weekend
days still get a row (hours 0, a short "on leave" / "weekend, no work
logged" description) so the sheet has no silent holes. Work through
`merged.json` day by day:

- **Commit day** (`is_gap: false`): summarize what the commits that day
  actually did, grounded in their subjects and files. Multiple small
  commits on one day usually collapse into one or two sentences, not a
  list.
- **Gap day** (`is_gap: true`): this is the "fill the gap intelligently"
  part the whole workflow exists for. Look at `nearest_next_commit_day`
  (usually the more informative one -- the push that *lands* the work
  almost always comes after the days spent on it) and, if useful,
  `nearest_prior_commit_day`. Use the size and nature of that commit as
  evidence of how many days it plausibly took, and write a progression
  across the gap days plus the commit day itself: an opening day
  ("started on ..."), a middle day if the gap is 2+ days ("kept at it,
  ran into ..." -- only invent a plausible obstacle if the diff itself
  hints at one, e.g. a fix commit right after; otherwise keep it neutral),
  and the commit day itself ("wrapped up ... and pushed it"). Don't
  invent specifics the diff doesn't support -- vague-but-true beats
  specific-but-fabricated. If a gap has no next commit at all (trailing
  gap at the end of the range, `nearest_next_commit_day: null`), fall back
  to the prior commit's work ("kept working on ...") without claiming
  anything landed.
- Split hours proportionally across projects on a multi-repo day using
  each repo's share of that day's changed lines as a rough guide, not
  strictly -- round to sane numbers (e.g. 5 + 3, not 4.7 + 3.3).

**Humanization rules -- apply these to every description, no exceptions:**

- Plain sentences only. No markdown: no `*`, `#`, `` ` ``, `_`, `~`, `|`,
  bullet dashes, em dashes. Only letters, numbers, spaces, commas,
  periods, apostrophes, and hyphens-within-words survive sanitization
  anyway (step 5 enforces this) -- so don't write them in the first place.
- First person, simple past tense, like someone filling this in quickly
  at the end of the day. One or two sentences per row.
- Vary sentence openings and structure across rows. Real timesheets don't
  start every line with "Worked on."
- Avoid stock AI phrasing: furthermore, additionally, leverage(d),
  utilize(d), delve(d), robust, seamless, comprehensive, "in order to",
  "it is worth noting", moreover. `build_timesheet.py` flags these as
  warnings -- treat any warning as something to rewrite, not ignore.
- Ground every sentence in the actual commit evidence. Never invent a
  meeting, a teammate, or a feature that isn't in the diff.

### 5. Render and sanitize

```
python scripts/build_timesheet.py \
  --input rows.json \
  --output-xlsx timesheet.xlsx --output-csv timesheet.csv \
  --target-hours-per-day 8
```

This writes both files and prints a JSON summary with a `warnings` list.
Two kinds of warnings matter:

- **"stripped disallowed characters"** -- your description had a
  character outside the allowed set and it was mechanically removed. Go
  fix the source text in `rows.json` and re-run rather than trusting the
  auto-stripped version; auto-stripping can leave awkward gaps (e.g. a
  removed em dash joining two clauses with no punctuation at all).
- **"reads as AI-generated"** -- rewrite that row's description by hand.
  This warning is a safety net, not a filter; don't skip past it.

Re-run this step (it's cheap and side-effect-free besides overwriting the
two output files) until `warnings` is empty or you've deliberately
accepted the remainder.

### 6. Hand it back to the user

Tell them where the `.xlsx` landed, the total hours, and the working/leave
day counts from the summary JSON. If anything looked ambiguous while
filling gaps (e.g. a 4-day gap before a huge commit with no other
evidence), say so rather than presenting a guess as fact.

## Notes

- **Re-running for a different person or period**: nothing here is
  memoized; every step is a fresh deterministic transform of its inputs,
  so re-running from step 1 with new dates/authors is always safe and
  correct -- there's no stale-cache risk to worry about.
- **Very large ranges or very active repos**: `collect_commits.py` pulls
  full history per repo and filters in Python (see `references/LESSONS.md`
  for why), so it scales with total repo history, not just the window
  size. For a repo with tens of thousands of commits this is still fast
  (git log itself is the bottleneck, not the Python parsing), but if it's
  ever a real problem, narrowing with a coarse `--since` on the git
  command *in addition to* the Python-side author-date filter (not
  instead of it) is the fix -- never replace the author-date filter with
  git's native one.
