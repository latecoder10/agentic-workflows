#!/usr/bin/env python3
"""Deterministic gap analysis for the git-timesheet workflow.

Takes the calendar.json from plan_calendar.py and the commits.json from
collect_commits.py and, for every non-Leave day, mechanically works out:

  - which commits (if any) landed that day, across all repos
  - if none landed that day (a "gap day"), the nearest commit day before
    and after it, with the distance in days and a summary of what that
    neighboring commit touched

That neighbor lookup is exactly the kind of thing that has one correct
answer and is tedious/error-prone for an agent to do by eye across several
repos -- so it's scripted. Turning the neighbor facts into a believable
day-by-day narrative, and deciding how to split hours across projects on a
multi-repo day, is left to the agent: that part genuinely needs judgment.
"""

import argparse
import datetime as dt
import json
from collections import defaultdict


def summarize_commits(entries):
    """entries: list of (repo_name, commit_dict) -> compact summary."""
    out = []
    for repo_name, c in entries:
        out.append({
            "repo": repo_name,
            "hash": c["hash"][:10],
            "subject": c["subject"],
            "files_changed": c["files_changed"],
            "insertions_total": c["insertions_total"],
            "deletions_total": c["deletions_total"],
            "top_files": [f["path"] for f in c["files"][:8]],
        })
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calendar", required=True, help="path to plan_calendar.py output")
    p.add_argument("--commits", required=True, help="path to collect_commits.py output")
    p.add_argument("--out", help="write JSON here instead of stdout")
    args = p.parse_args()

    with open(args.calendar, "r", encoding="utf-8") as f:
        calendar = json.load(f)
    with open(args.commits, "r", encoding="utf-8") as f:
        commits_doc = json.load(f)

    by_date = defaultdict(list)
    all_dates = set()
    for repo in commits_doc["repos"]:
        for c in repo["commits"]:
            by_date[c["date"]].append((repo["name"], c))
            all_dates.add(c["date"])
    sorted_commit_dates = sorted(all_dates)

    def nearest(target_iso, direction):
        target = dt.date.fromisoformat(target_iso)
        best = None
        for d_iso in sorted_commit_dates:
            d = dt.date.fromisoformat(d_iso)
            if direction == "prior" and d < target:
                if best is None or d > dt.date.fromisoformat(best):
                    best = d_iso
            elif direction == "next" and d > target:
                if best is None or d < dt.date.fromisoformat(best):
                    best = d_iso
        if best is None:
            return None
        days_away = abs((dt.date.fromisoformat(best) - target).days)
        return {
            "date": best,
            "days_away": days_away,
            "commits": summarize_commits(by_date[best]),
        }

    timeline = []
    for day in calendar["days"]:
        iso = day["date"]
        entries = by_date.get(iso, [])
        row = {
            "date": iso,
            "weekday": day["weekday"],
            "status": day["status"],
        }
        if day["status"] == "Leave":
            row["commits"] = summarize_commits(entries)
            row["commits_found_on_leave_day"] = len(entries) > 0
            row["is_gap"] = False
        else:
            if entries:
                row["commits"] = summarize_commits(entries)
                row["is_gap"] = False
            else:
                row["commits"] = []
                row["is_gap"] = True
                row["nearest_prior_commit_day"] = nearest(iso, "prior")
                row["nearest_next_commit_day"] = nearest(iso, "next")
        timeline.append(row)

    doc = {
        "commit_dates": sorted_commit_dates,
        "timeline": timeline,
    }

    text = json.dumps(doc, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        gap_days = sum(1 for r in timeline if r.get("is_gap"))
        print(json.dumps({"wrote": args.out, "days": len(timeline), "gap_days": gap_days}))
    else:
        print(text)


if __name__ == "__main__":
    main()
