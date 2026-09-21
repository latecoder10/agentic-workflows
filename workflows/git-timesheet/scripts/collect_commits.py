#!/usr/bin/env python3
"""Deterministic git history collector for the git-timesheet workflow.

Pulls commit metadata + per-file numstat for one or more local repos over a
date window, and prints a single structured JSON document to stdout (or
--out). Does no interpretation of *what* the work was -- that's the agent's
job in a later step.
"""

import argparse
import datetime as dt
import json
import subprocess
import sys

RECORD_SEP = "\x02"
FIELD_SEP = "\x1f"


def run_git_log(repo, authors):
    # Deliberately no --since/--until here: those filter on *committer* date,
    # not author date. Rebased, cherry-picked, or re-pushed commits (extremely
    # common in exactly the "worked for days, pushed later" flow this workflow
    # exists for) end up with a committer date that has nothing to do with the
    # day the work actually happened. We pull full history and filter on the
    # parsed author date (%ad) in Python instead -- see references/LESSONS.md.
    pretty = FIELD_SEP.join(["%H", "%ad", "%cd", "%an", "%ae", "%s"])
    cmd = [
        "git", "-C", repo, "log",
        "--no-merges",
        "--date=short",
        f"--pretty=format:{RECORD_SEP}{pretty}",
        "--numstat",
    ]
    for a in authors:
        cmd.append(f"--author={a}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"git log failed for {repo}: {result.stderr.strip()}")
    return result.stdout


def parse_log_output(raw):
    commits = []
    chunks = [c for c in raw.split(RECORD_SEP) if c.strip()]
    for chunk in chunks:
        lines = chunk.splitlines()
        if not lines:
            continue
        header = lines[0]
        parts = header.split(FIELD_SEP)
        if len(parts) < 6:
            continue
        commit_hash, date, committer_date, author_name, author_email, subject = parts[:6]
        files = []
        insertions_total = 0
        deletions_total = 0
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) != 3:
                continue
            ins, dele, path = fields
            binary = ins == "-" or dele == "-"
            ins_n = 0 if binary else int(ins)
            del_n = 0 if binary else int(dele)
            insertions_total += ins_n
            deletions_total += del_n
            files.append({
                "path": path,
                "insertions": ins_n,
                "deletions": del_n,
                "binary": binary,
            })
        commits.append({
            "hash": commit_hash,
            "date": date,
            "committer_date": committer_date,
            "author_name": author_name,
            "author_email": author_email,
            "subject": subject,
            "files": files,
            "files_changed": len(files),
            "insertions_total": insertions_total,
            "deletions_total": deletions_total,
        })
    commits.sort(key=lambda c: (c["date"], c["hash"]))
    return commits


def is_git_repo(path):
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", action="append", required=True, help="path to a git repo (repeatable)")
    p.add_argument("--since", required=True, help="YYYY-MM-DD, start of the reporting window")
    p.add_argument("--until", required=True, help="YYYY-MM-DD, end of the reporting window (inclusive)")
    p.add_argument("--author", action="append", default=[], help="git --author pattern, repeatable (OR'd); omit to include all authors")
    p.add_argument("--lookback-days", type=int, default=7, help="widen the window backwards so gap-day analysis has neighbor context")
    p.add_argument("--lookahead-days", type=int, default=7, help="widen the window forwards so gap-day analysis has neighbor context")
    p.add_argument("--out", help="write JSON here instead of stdout")
    args = p.parse_args()

    since_d = dt.date.fromisoformat(args.since)
    until_d = dt.date.fromisoformat(args.until)
    window_since = (since_d - dt.timedelta(days=args.lookback_days)).isoformat()
    window_until = (until_d + dt.timedelta(days=args.lookahead_days)).isoformat()

    window_since_d = dt.date.fromisoformat(window_since)
    window_until_d = dt.date.fromisoformat(window_until)

    repos_out = []
    warnings = []
    for repo in args.repo:
        if not is_git_repo(repo):
            warnings.append(f"skipped {repo}: not a git repository")
            continue
        raw = run_git_log(repo, args.author)
        all_commits = parse_log_output(raw)
        commits = [
            c for c in all_commits
            if window_since_d <= dt.date.fromisoformat(c["date"]) <= window_until_d
        ]
        rewritten = sum(1 for c in commits if c.get("committer_date") != c["date"])
        if rewritten:
            warnings.append(
                f"{repo}: {rewritten} commit(s) in window have a committer date different from "
                f"their author date (rebased/re-pushed) -- author date was used for placement, as intended"
            )
        repos_out.append({
            "path": repo,
            "name": repo.rstrip("/\\").split("/")[-1].split("\\")[-1],
            "commit_count": len(commits),
            "commits": commits,
        })

    doc = {
        "requested_since": args.since,
        "requested_until": args.until,
        "window_since": window_since,
        "window_until": window_until,
        "authors_filter": args.author,
        "repos": repos_out,
        "warnings": warnings,
    }

    text = json.dumps(doc, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(json.dumps({"wrote": args.out, "repo_count": len(repos_out), "warnings": warnings}))
    else:
        print(text)


if __name__ == "__main__":
    main()
