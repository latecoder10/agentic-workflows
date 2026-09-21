#!/usr/bin/env python3
"""Deterministic calendar builder for the git-timesheet workflow.

Turns a date range + leave dates into a day-by-day status list. Pure date
arithmetic -- no git, no judgment -- so the agent never has to hand-count
weekdays or reconcile leave overlaps itself.
"""

import argparse
import datetime as dt
import json

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", required=True, help="YYYY-MM-DD, first day of the period")
    p.add_argument("--until", required=True, help="YYYY-MM-DD, last day of the period (inclusive)")
    p.add_argument("--leave", action="append", default=[], help="YYYY-MM-DD leave/off day, repeatable")
    p.add_argument("--include-weekends", action="store_true", help="treat Sat/Sun as Working by default instead of Weekend (override per-day later if commits show up on a weekend anyway)")
    p.add_argument("--out", help="write JSON here instead of stdout")
    args = p.parse_args()

    since_d = dt.date.fromisoformat(args.since)
    until_d = dt.date.fromisoformat(args.until)
    if until_d < since_d:
        raise SystemExit("error: --until is before --since")

    leave_set = set(args.leave)
    unknown_leave = [d for d in leave_set if not _valid_date(d)]
    if unknown_leave:
        raise SystemExit(f"error: invalid --leave date(s): {unknown_leave}")

    days = []
    cursor = since_d
    while cursor <= until_d:
        iso = cursor.isoformat()
        weekday_name = WEEKDAY_NAMES[cursor.weekday()]
        is_weekend = cursor.weekday() >= 5
        if iso in leave_set:
            status = "Leave"
        elif is_weekend and not args.include_weekends:
            status = "Weekend"
        else:
            status = "Working"
        days.append({"date": iso, "weekday": weekday_name, "status": status})
        cursor += dt.timedelta(days=1)

    used_leave = {d["date"] for d in days if d["status"] == "Leave"}
    unused_leave = sorted(leave_set - used_leave)

    doc = {
        "since": args.since,
        "until": args.until,
        "total_days": len(days),
        "working_days": sum(1 for d in days if d["status"] == "Working"),
        "weekend_days": sum(1 for d in days if d["status"] == "Weekend"),
        "leave_days": sum(1 for d in days if d["status"] == "Leave"),
        "leave_dates_outside_range": unused_leave,
        "days": days,
    }

    text = json.dumps(doc, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(json.dumps({"wrote": args.out, "working_days": doc["working_days"], "leave_days": doc["leave_days"]}))
    else:
        print(text)


def _valid_date(s):
    try:
        dt.date.fromisoformat(s)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
