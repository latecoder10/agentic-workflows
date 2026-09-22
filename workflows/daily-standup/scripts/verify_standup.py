#!/usr/bin/env python3
"""Deterministic validator and renderer for the daily-standup workflow.

Takes the agent's standup.json, verifies structure and brevity constraints,
checks for banned AI-puffery phrases and raw commit hashes, and formats
the final output into clean Markdown, Slack/Teams mrkdwn, or plain text.

Deterministic safety net -- prevents agents from writing verbose essays,
hallucinating blockers, or using robotic corporate jargon.
"""

import argparse
import json
import os
import re
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Tell-tale AI buzzwords and corporate filler phrases that signal an LLM
# generated an ungrounded or bloated status update.
AI_BUZZWORDS = [
    "spearhead", "spearheaded", "spearheading",
    "orchestrate", "orchestrated", "orchestrating",
    "delve", "delved", "delving",
    "seamless", "seamlessly",
    "robust", "robustly",
    "pivotal", "holistic",
    "testament", "tapestry",
    "leverage", "leveraged", "leveraging",
    "synergy", "synergies",
    "streamline", "streamlined", "streamlining",
    "meticulous", "meticulously",
    "comprehensive", "comprehensively",
    "furthermore", "additionally",
    "it is worth noting", "it's worth noting",
    "in order to", "serves to",
]

RAW_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
WORD_COUNT_WARN_THRESHOLD = 25
WORD_COUNT_MAX_THRESHOLD = 40
MAX_BULLETS_PER_SECTION = 4


def sanitize_text(text):
    """Normalize whitespace and strip markdown formatting from plain bullet text."""
    if not text:
        return ""
    # Strip bullet indicators if user accidentally put them in text
    cleaned = re.sub(r"^[\s*\-•]+\s*", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def check_bullet(bullet, section_name):
    """Check an individual bullet for length, AI clichés, and raw hashes."""
    warnings = []
    errors = []

    words = bullet.split()
    word_count = len(words)

    if word_count > WORD_COUNT_MAX_THRESHOLD:
        errors.append(
            f"[{section_name}] Bullet exceeds {WORD_COUNT_MAX_THRESHOLD} words ({word_count} words): \"{bullet[:50]}...\""
        )
    elif word_count > WORD_COUNT_WARN_THRESHOLD:
        warnings.append(
            f"[{section_name}] Bullet is somewhat verbose ({word_count} words; recommend <= {WORD_COUNT_WARN_THRESHOLD}): \"{bullet[:50]}...\""
        )

    lowered = bullet.lower()
    for phrase in AI_BUZZWORDS:
        # Match whole word / phrase boundaries
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, lowered):
            warnings.append(
                f"[{section_name}] Contains banned AI-filler phrase '{phrase}'. Rephrase in plain, direct developer language: \"{bullet}\""
            )

    sha_matches = RAW_SHA_RE.findall(bullet)
    if sha_matches:
        warnings.append(
            f"[{section_name}] Contains raw commit hash '{sha_matches[0]}'. Standup updates should name features or components, not commit hashes."
        )

    return errors, warnings


def validate_standup(data, activity_data=None):
    """Validate standup data structure, content rules, and optional activity grounding."""
    errors = []
    warnings = []

    required_sections = ["yesterday", "today", "blockers"]
    for sec in required_sections:
        if sec not in data:
            errors.append(f"Missing required section '{sec}'.")
            continue

        val = data[sec]
        if not isinstance(val, list):
            errors.append(f"Section '{sec}' must be a list of bullet strings.")
            continue

        if len(val) == 0:
            errors.append(f"Section '{sec}' cannot be empty (for blockers with none, use ['None']).")
            continue

        if len(val) > MAX_BULLETS_PER_SECTION:
            warnings.append(
                f"Section '{sec}' has {len(val)} bullets (recommend at most {MAX_BULLETS_PER_SECTION} for standup brevity)."
            )

        for bullet in val:
            if not isinstance(bullet, str) or not bullet.strip():
                errors.append(f"Section '{sec}' contains empty or non-string bullet.")
                continue
            b_errs, b_warns = check_bullet(bullet.strip(), sec)
            errors.extend(b_errs)
            warnings.extend(b_warns)

    # Optional activity grounding check
    if activity_data and "repos" in activity_data:
        known_repos = [r.get("name", "").lower() for r in activity_data.get("repos", [])]
        has_activity = any(r.get("commits_in_window", 0) > 0 for r in activity_data.get("repos", []))
        yesterday_bullets = data.get("yesterday", [])
        if has_activity and len(yesterday_bullets) == 1 and yesterday_bullets[0].strip().lower() in ("none", "no updates"):
            warnings.append(
                "Activity data shows completed commits in the lookback window, but 'yesterday' reports no updates."
            )

    return errors, warnings


def render_markdown(data):
    """Render standup into standard GitHub Markdown format."""
    lines = []
    date_str = data.get("date", "")
    author_str = data.get("author", "")

    header_parts = ["Standup"]
    if date_str:
        header_parts.append(date_str)
    if author_str:
        header_parts.append(f"({author_str})")

    lines.append(f"## {' - '.join(header_parts)}")
    lines.append("")

    lines.append("### Yesterday")
    for b in data.get("yesterday", []):
        lines.append(f"- {sanitize_text(b)}")
    lines.append("")

    lines.append("### Today")
    for b in data.get("today", []):
        lines.append(f"- {sanitize_text(b)}")
    lines.append("")

    lines.append("### Blockers")
    for b in data.get("blockers", []):
        lines.append(f"- {sanitize_text(b)}")
    lines.append("")

    return "\n".join(lines)


def render_slack(data):
    """Render standup into Slack / Teams mrkdwn format."""
    lines = []
    date_str = data.get("date", "")
    author_str = data.get("author", "")

    title = "*Daily Standup*"
    if date_str:
        title += f" — {date_str}"
    if author_str:
        title += f" ({author_str})"
    lines.append(title)
    lines.append("")

    lines.append("*Yesterday:*")
    for b in data.get("yesterday", []):
        lines.append(f"• {sanitize_text(b)}")
    lines.append("")

    lines.append("*Today:*")
    for b in data.get("today", []):
        lines.append(f"• {sanitize_text(b)}")
    lines.append("")

    lines.append("*Blockers:*")
    for b in data.get("blockers", []):
        lines.append(f"• {sanitize_text(b)}")

    return "\n".join(lines)


def render_plain(data):
    """Render standup into clean plain text format."""
    lines = []
    lines.append("YESTERDAY:")
    for b in data.get("yesterday", []):
        lines.append(f"  - {sanitize_text(b)}")
    lines.append("")
    lines.append("TODAY:")
    for b in data.get("today", []):
        lines.append(f"  - {sanitize_text(b)}")
    lines.append("")
    lines.append("BLOCKERS:")
    for b in data.get("blockers", []):
        lines.append(f"  - {sanitize_text(b)}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Verify and format daily standup JSON into Markdown, Slack mrkdwn, or plain text."
    )
    parser.add_argument(
        "input",
        help="Path to standup.json file to validate and render.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "slack", "plain"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--activity",
        help="Optional path to activity.json for grounding validation.",
    )
    parser.add_argument(
        "--out",
        help="Path to write formatted standup output. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as fatal errors.",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: Input file '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON from '{args.input}': {e}", file=sys.stderr)
        sys.exit(1)

    activity_data = None
    if args.activity and os.path.isfile(args.activity):
        try:
            with open(args.activity, "r", encoding="utf-8") as f:
                activity_data = json.load(f)
        except Exception:
            pass

    errors, warnings = validate_standup(data, activity_data)

    for warn in warnings:
        print(f"WARNING: {warn}", file=sys.stderr)

    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)

    if errors or (args.strict and warnings):
        print(
            f"Standup validation failed ({len(errors)} error(s), {len(warnings)} warning(s)). Please revise input.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Render
    if args.format == "markdown":
        rendered = render_markdown(data)
    elif args.format == "slack":
        rendered = render_slack(data)
    else:
        rendered = render_plain(data)

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        print(f"Rendered standup ({args.format}) written to {args.out}", file=sys.stderr)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
