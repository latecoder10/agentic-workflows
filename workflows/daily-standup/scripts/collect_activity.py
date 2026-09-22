#!/usr/bin/env python3
"""Deterministic activity collector for the daily-standup workflow.

Collects git commit history, current active branch, staged/unstaged working tree
diffs, stashes, and unpushed commits across one or more local repos over a
standup lookback window (automatically handling the Monday -> Friday lookback trap).

Outputs a structured JSON document to stdout or a specified file (--out).
Does no interpretation of narrative or tone -- that is the agent's judgment
step.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RECORD_SEP = "\x02"
FIELD_SEP = "\x1f"


def is_git_repo(path):
    """Check if path is inside a valid git working tree."""
    try:
        res = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_default_author(repo):
    """Attempt to detect the local git user's name and email."""
    name = ""
    email = ""
    try:
        res_name = subprocess.run(
            ["git", "-C", repo, "config", "user.name"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if res_name.returncode == 0:
            name = res_name.stdout.strip()
    except Exception:
        pass

    try:
        res_email = subprocess.run(
            ["git", "-C", repo, "config", "user.email"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if res_email.returncode == 0:
            email = res_email.stdout.strip()
    except Exception:
        pass

    authors = []
    if name:
        authors.append(name)
    if email and email not in authors:
        authors.append(email)
    return authors


def get_current_branch(repo):
    """Return the active branch name or detached HEAD indicator."""
    res = subprocess.run(
        ["git", "-C", repo, "branch", "--show-current"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    branch = res.stdout.strip()
    if branch:
        return branch
    # Detached HEAD check
    res_head = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    head = res_head.stdout.strip()
    return f"DETACHED-HEAD@{head}" if head else "UNKNOWN"


def get_working_tree_status(repo):
    """Inspect staged, unstaged, and untracked changes in the working tree."""
    res = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain=v1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    staged = []
    unstaged = []
    untracked = []

    for line in lines:
        if len(line) < 3:
            continue
        index_status = line[0]
        work_tree_status = line[1]
        file_path = line[3:].strip()

        if index_status == "?":
            untracked.append(file_path)
            continue

        if index_status not in (" ", "?"):
            staged.append({"path": file_path, "status": index_status})

        if work_tree_status not in (" ", "?"):
            unstaged.append({"path": file_path, "status": work_tree_status})

    # Short diff stats
    staged_diffstat = ""
    res_staged = subprocess.run(
        ["git", "-C", repo, "diff", "--cached", "--stat"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res_staged.returncode == 0 and res_staged.stdout.strip():
        stat_lines = res_staged.stdout.strip().splitlines()
        staged_diffstat = stat_lines[-1].strip() if stat_lines else ""

    unstaged_diffstat = ""
    res_unstaged = subprocess.run(
        ["git", "-C", repo, "diff", "--stat"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res_unstaged.returncode == 0 and res_unstaged.stdout.strip():
        stat_lines = res_unstaged.stdout.strip().splitlines()
        unstaged_diffstat = stat_lines[-1].strip() if stat_lines else ""

    return {
        "staged_files": staged,
        "unstaged_files": unstaged,
        "untracked_files": untracked,
        "staged_diffstat": staged_diffstat,
        "unstaged_diffstat": unstaged_diffstat,
        "is_dirty": bool(staged or unstaged or untracked),
    }


def get_stashes(repo, limit=5):
    """Retrieve recent stash entries."""
    res = subprocess.run(
        ["git", "-C", repo, "stash", "list", f"-n{limit}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stashes = []
    if res.returncode == 0 and res.stdout.strip():
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(":", 2)
            stash_id = parts[0].strip() if len(parts) > 0 else line
            branch_info = parts[1].strip() if len(parts) > 1 else ""
            desc = parts[2].strip() if len(parts) > 2 else ""
            stashes.append({
                "id": stash_id,
                "context": branch_info,
                "description": desc,
            })
    return stashes


def get_unpushed_commits(repo):
    """Check for local commits that have not been pushed to upstream."""
    res_upstream = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--abbrev-ref", "@{u}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res_upstream.returncode != 0:
        return {"has_upstream": False, "upstream_branch": None, "commits": []}

    upstream = res_upstream.stdout.strip()
    res_log = subprocess.run(
        ["git", "-C", repo, "log", "--oneline", f"{upstream}..HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    commits = []
    if res_log.returncode == 0 and res_log.stdout.strip():
        for line in res_log.stdout.strip().splitlines():
            parts = line.strip().split(" ", 1)
            commit_hash = parts[0]
            msg = parts[1] if len(parts) > 1 else ""
            commits.append({"hash": commit_hash, "subject": msg})

    return {
        "has_upstream": True,
        "upstream_branch": upstream,
        "commits": commits,
        "unpushed_count": len(commits),
    }


def parse_commits(raw_log, since_date, until_date, authors):
    """Parse raw git log output with numstat and filter by author date and author identities."""
    commits = []
    chunks = [c for c in raw_log.split(RECORD_SEP) if c.strip()]
    author_regexes = [re.compile(re.escape(a), re.IGNORECASE) for a in authors] if authors else []

    divergent_committer_dates = 0

    for chunk in chunks:
        lines = chunk.splitlines()
        if not lines:
            continue
        header = lines[0]
        parts = header.split(FIELD_SEP)
        if len(parts) < 6:
            continue
        commit_hash, author_name, author_email, author_date, committer_date, subject = parts[:6]

        # Extract date portion YYYY-MM-DD
        author_day = author_date[:10] if len(author_date) >= 10 else author_date
        committer_day = committer_date[:10] if len(committer_date) >= 10 else committer_date

        if author_day != committer_day:
            divergent_committer_dates += 1

        # Date window check on AUTHOR date
        if since_date and author_day < since_date:
            continue
        if until_date and author_day > until_date:
            continue

        # Author identity check
        if author_regexes:
            matched = any(
                r.search(author_name) or r.search(author_email)
                for r in author_regexes
            )
            if not matched:
                continue

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
            "author_date": author_day,
            "committer_date": committer_day,
            "author_name": author_name,
            "author_email": author_email,
            "subject": subject,
            "files_changed": len(files),
            "insertions": insertions_total,
            "deletions": deletions_total,
            "files": files,
        })

    # Sort chronological by author date then hash
    commits.sort(key=lambda c: (c["author_date"], c["hash"]))
    return commits, divergent_committer_dates


def extract_top_components(commits, working_tree):
    """Extract touched top-level modules/directories to give agent high-level structure."""
    dirs = {}
    for c in commits:
        for f in c.get("files", []):
            p = f.get("path", "")
            parts = p.replace("\\", "/").split("/")
            top = parts[0] if len(parts) > 1 else "(root)"
            dirs[top] = dirs.get(top, 0) + 1

    for category in ("staged_files", "unstaged_files"):
        for f in working_tree.get(category, []):
            p = f.get("path", "")
            parts = p.replace("\\", "/").split("/")
            top = parts[0] if len(parts) > 1 else "(root)"
            dirs[top] = dirs.get(top, 0) + 1

    sorted_dirs = sorted(dirs.items(), key=lambda x: x[1], reverse=True)
    return [d[0] for d in sorted_dirs[:5]]


def determine_date_window(since_arg, until_arg, days_arg):
    """Determine the default or explicit date window.

    Special attention to the Monday standup trap:
    If running on Monday and no --since is given, lookback starts on Friday (3 days prior).
    Otherwise defaults to yesterday (1 day prior).
    """
    today = dt.date.today()
    is_monday = today.weekday() == 0

    if until_arg:
        until_date = dt.datetime.strptime(until_arg, "%Y-%m-%d").date()
    else:
        until_date = today

    if since_arg:
        since_date = dt.datetime.strptime(since_arg, "%Y-%m-%d").date()
        is_monday_lookback = False
    elif days_arg is not None:
        since_date = until_date - dt.timedelta(days=days_arg)
        is_monday_lookback = False
    else:
        if is_monday:
            # Monday lookback: covers Friday, Saturday, Sunday
            since_date = today - dt.timedelta(days=3)
            is_monday_lookback = True
        else:
            # Standard lookback: covers yesterday
            since_date = today - dt.timedelta(days=1)
            is_monday_lookback = False

    return since_date.isoformat(), until_date.isoformat(), is_monday_lookback


def main():
    parser = argparse.ArgumentParser(
        description="Collect git commits, working copy state, stashes, and branches for daily standup."
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repos",
        help="Path to a git repository (repeatable for multiple repos). Defaults to current directory.",
    )
    parser.add_argument(
        "--author",
        action="append",
        dest="authors",
        help="Author name or email substring to match (repeatable). Defaults to repo git user config.",
    )
    parser.add_argument(
        "--all-authors",
        action="store_true",
        help="Do not filter commits by author (useful for solo repositories).",
    )
    parser.add_argument(
        "--since",
        help="Start date YYYY-MM-DD (inclusive). Defaults to yesterday, or Friday if today is Monday.",
    )
    parser.add_argument(
        "--until",
        help="End date YYYY-MM-DD (inclusive). Defaults to today.",
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Override lookback window to N days prior to --until.",
    )
    parser.add_argument(
        "--out",
        help="Path to write JSON output. Prints to stdout if omitted.",
    )

    args = parser.parse_args()

    repo_paths = args.repos or ["."]
    since_date, until_date, is_monday_lookback = determine_date_window(
        args.since, args.until, args.days
    )

    authors = args.authors or []
    if not authors and not args.all_authors:
        # Try to infer default author from first valid repo
        for r in repo_paths:
            if is_git_repo(r):
                inferred = get_default_author(r)
                if inferred:
                    authors = inferred
                    break

    warnings = []
    repo_results = []

    for r in repo_paths:
        abs_path = os.path.abspath(r)
        repo_name = os.path.basename(abs_path) or abs_path

        if not is_git_repo(abs_path):
            warnings.append(f"Directory '{r}' is not a valid git repository (skipped).")
            continue

        branch = get_current_branch(abs_path)
        working_tree = get_working_tree_status(abs_path)
        stashes = get_stashes(abs_path)
        unpushed = get_unpushed_commits(abs_path)

        # Pull raw git log
        # Pull with buffer around since date to avoid boundary issues
        pretty = FIELD_SEP.join(["%H", "%an", "%ae", "%ad", "%cd", "%s"])
        cmd = [
            "git", "-C", abs_path, "log",
            "--no-merges",
            "--date=short",
            f"--pretty=format:{RECORD_SEP}{pretty}",
            "--numstat",
            "-n", "100",  # limit recent commits to keep quick
        ]
        log_res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if log_res.returncode != 0:
            warnings.append(f"Failed to query git log for '{r}': {log_res.stderr.strip()}")
            commits = []
            divergent = 0
        else:
            commits, divergent = parse_commits(
                log_res.stdout,
                since_date,
                until_date,
                authors if not args.all_authors else [],
            )
            if divergent > 0:
                warnings.append(
                    f"Repo '{repo_name}': {divergent} commits had divergent author vs committer dates (author date was used)."
                )

        top_components = extract_top_components(commits, working_tree)

        repo_results.append({
            "name": repo_name,
            "path": abs_path,
            "current_branch": branch,
            "commits_in_window": len(commits),
            "commits": commits,
            "working_tree": working_tree,
            "stashes": stashes,
            "unpushed_commits": unpushed,
            "top_components_touched": top_components,
        })

    payload = {
        "generated_at": dt.datetime.now().isoformat(),
        "period": {
            "since": since_date,
            "until": until_date,
            "is_monday_lookback": is_monday_lookback,
        },
        "authors_filtered": authors if not args.all_authors else ["ALL"],
        "warnings": warnings,
        "repo_count": len(repo_results),
        "repos": repo_results,
    }

    formatted_json = json.dumps(payload, indent=2)

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(formatted_json + "\n")
        print(
            f"Wrote standup activity for {len(repo_results)} repo(s) covering {since_date} to {until_date} to {args.out}",
            file=sys.stderr,
        )
    else:
        print(formatted_json)


if __name__ == "__main__":
    main()
