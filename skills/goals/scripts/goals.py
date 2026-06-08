#!/usr/bin/env python3
"""Read the operator's goals file and report its freshness as JSON.

The goals skill is mostly agent reasoning (eliciting, refining, coaching, and
writing the markdown). The one thing worth scripting is the mechanical bit the
agent shouldn't eyeball: locating the goals file, parsing its frontmatter, and
doing the date math that decides whether it's time to nudge a re-baseline.

So this script does exactly that and nothing more. `status` prints a compact
JSON snapshot the agent then acts on; the agent itself does all reading,
writing, and reasoning over the file with its normal file tools. Stdlib only.

Storage layout (under --dir, default $GOALS_DIR or /data/vault/goals):
    goals.md            the live goals (YAML frontmatter + a section per horizon)
    history/            dated snapshots of prior versions (goals-YYYY-MM-DD.md)

Only flat frontmatter keys are parsed (last_updated, coaching_intensity, …);
anything nested or per-horizon lives in the body, which the agent manages.

Usage:
    goals.py status [--dir PATH] [--stale-days 30]
"""
import argparse
import datetime as dt
import json
import os
import sys

DEFAULT_DIR = os.environ.get("GOALS_DIR", "/data/vault/goals")
VALID_INTENSITY = ("light", "moderate", "assertive")


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def parse_frontmatter(text):
    """Pull a flat `key: value` YAML frontmatter block delimited by `---` lines.

    Deliberately dumb: no nesting, no lists, no multiline. The goals file keeps
    its frontmatter flat for exactly this reason; richer structure goes in the
    body where the agent reads it directly.
    """
    fm = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fm
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            fm[key] = val
    return fm


def parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s.strip())
    except ValueError:
        return None


def cmd_status(args):
    today = dt.date.today()
    goals_dir = args.dir
    path = os.path.join(goals_dir, "goals.md")
    history_dir = os.path.join(goals_dir, "history")

    out = {
        "dir": goals_dir,
        "path": path,
        "today": today.isoformat(),
        "stale_days": args.stale_days,
        "exists": False,
        "last_updated": None,
        "days_since_update": None,
        "stale": False,
        "coaching_intensity": "moderate",  # default until the file sets one
        "history_count": 0,
    }

    if os.path.isdir(history_dir):
        out["history_count"] = sum(
            1 for f in os.listdir(history_dir) if f.endswith(".md")
        )

    if not os.path.isfile(path):
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    out["exists"] = True
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        die(f"could not read {path}: {e}")

    fm = parse_frontmatter(text)

    intensity = (fm.get("coaching_intensity") or "").lower()
    if intensity in VALID_INTENSITY:
        out["coaching_intensity"] = intensity

    last = parse_date(fm.get("last_updated"))
    if last:
        out["last_updated"] = last.isoformat()
        days = (today - last).days
        out["days_since_update"] = days
        out["stale"] = days >= args.stale_days

    print(json.dumps(out, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Goals file freshness reporter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="report whether goals exist and how fresh they are")
    s.add_argument("--dir", default=DEFAULT_DIR,
                   help=f"goals directory (default {DEFAULT_DIR})")
    s.add_argument("--stale-days", type=int, default=30,
                   help="age in days at which to flag a re-baseline nudge (default 30)")
    args = ap.parse_args()

    if args.cmd == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
