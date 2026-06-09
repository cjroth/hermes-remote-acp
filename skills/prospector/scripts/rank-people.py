#!/usr/bin/env python3
"""Rank the people in the vault by who's most strategic to move toward *now*.

The deterministic counterpart to the prospector skill's strategic reasoning —
same role `rank-roles.py` plays for careerbot. The agent maintains one markdown
file per person under `people/<status>/<slug>.md` with structured frontmatter;
this script reads that frontmatter, computes a composite `priority_score`, and
writes a ranked table to `prospects.md` at the vault root (and to stdout). Run
it on every pass so the ranking always reflects the latest graph. Stdlib only.

The scoring model (encodes the research-backed heuristics — see
references/playbook.md):

    priority =
        3.0 * goal_relevance     # how directly this person serves a current goal
      + 1.5 * fit_value          # influence / super-connector (bridges structural holes)
      + 1.5 * reachability       # relationship > warm-intro path > cold (warm ~10-20x cold)
      + 1.0 * relationship       # tier: stranger < friendly < strong < advocate
      + 2.0 * trigger            # active trigger event, recency-decayed (reach *now*)
      + 1.5 * dormant_bonus      # high past-closeness gone quiet = highest-ROI reconnection
      - 2.0 * status_gap         # prominence above the operator → implausible to reach cold
      - 2.0 * recent_contact     # touched within cadence → don't pester
      - 1.0 * give_ask_imbalance # asked >> gave → relational, not transactional
      + priority_override        # agent's manual thumb on the scale

The status_gap penalty encodes the operator's position relative to the target.
A billion-dollar-company CEO won't answer a cold note from an individual builder
no matter how good the message — so prominent/elite targets get heavily penalized
*when the reach is cold*. The penalty is mostly waived when a warm path or an
existing relationship bridges the gap, and softened when there's a `specific_ask`
(a concrete, mutually-valuable reason that earns the reach — e.g. "would you
angel-invest in my seed round?"). The operator's own standing is the reference
point: today an early-stage individual builder, so the gap is real; as their
standing grows (traction, a raise, a known company), lower the targets' relative
prominence rather than the penalty.

Every subscore is 0–100 before weighting. The script gives a stable ordering;
the agent layers the actual strategy (mode, path, message) on top.

Frontmatter fields the script reads (everything else lives in the body):
    category               cofounder|investor|customer|connector|mentor|recruiter|peer|operator|other
    relationship_strength  stranger|friendly|strong|advocate
    last_touch             YYYY-MM-DD            (empty/absent = never contacted)
    cadence_days           int                   (tier reconnect rhythm; default 30)
    trigger                free text             (presence = an active reason to reach now)
    trigger_date           YYYY-MM-DD
    has_warm_path          true|false            (a 1–2 hop intro path exists; details in body)
    super_connector        true|false            (bridges clusters the user lacks access to)
    prominence             peer|notable|prominent|elite   (their reach/stature vs. the operator)
    specific_ask           true|false            (a concrete, mutually-valuable reason that earns a big reach)
    primary_channel        email|linkedin|x|...  (display only)
    gives / asks           int                   (give-first ledger)
    goal_served            free text             (display: which goal/target this advances)
    priority_override      int                   (added to the final score; pin or bury someone)

Status comes from the parent folder name, not frontmatter.

Usage:
    rank-people.py [--dir /data/vault/people] [--out /data/vault/prospects.md]
"""
import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = os.environ.get("PEOPLE_DIR", "/data/vault/people")
DEFAULT_OUT = os.environ.get("PROSPECTS_OUT", "/data/vault/prospects.md")

# Goal-derived category weights (0–100). These mirror the current strategic
# direction in goals.md (the founder path: cofounders, investors, and early
# customers lead; the "better company" path keeps recruiters/operators in play;
# connectors and mentors open paths). Keep these in sync with goals.md as the
# direction shifts — same idea as the baked profile in careerbot's rank-roles.py.
CATEGORY_WEIGHT = {
    "cofounder": 95,
    "investor": 80,
    "customer": 80,      # design partner / early customer for the product thesis
    "connector": 72,     # opens many paths (super-connector / broker)
    "mentor": 65,
    "recruiter": 60,     # the "better company" path
    "operator": 52,
    "peer": 50,
    "other": 30,
}

STRENGTH_POINTS = {"stranger": 0, "friendly": 40, "strong": 70, "advocate": 100}
# Target's stature/reach relative to the operator. Drives the cold-reach status
# penalty: the higher the gap, the less plausible a cold note is. peer = same
# rough standing; elite = a-list founder/VC/CEO drowning in inbound.
PROMINENCE_POINTS = {"peer": 0, "notable": 33, "prominent": 67, "elite": 100}
RELATIONSHIP_STATUSES = {"nurturing", "in-conversation"}
DEFAULT_CADENCE = 30
DORMANT_SILENCE_DAYS = 180  # strong/advocate tie silent this long = reactivation play


def parse_frontmatter(text):
    """Pull flat `key: value` frontmatter delimited by `---` lines (no nesting).

    Mirrors the dumb-but-robust parser in careerbot. Anything structured
    (intro-path slugs, channel handles, history) lives in the body, which the
    agent reads directly — the script only needs these flat scalars.
    """
    fm = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fm
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = re.match(r'^(\w+):\s*["\']?(.*?)["\']?\s*$', ln)
        if m and m.group(1):
            fm[m.group(1)] = m.group(2).strip()
    return fm


def as_bool(v):
    return str(v).strip().lower() in ("true", "yes", "1")


def as_int(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def recency_factor(days):
    """Signal value decays with age (research: ~3x at 7d vs 30d; halve past 90d)."""
    if days is None:
        return 0.0
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.6
    if days <= 90:
        return 0.3
    return 0.1


def score_person(fm, status, today):
    category = (fm.get("category") or "other").lower()
    strength = (fm.get("relationship_strength") or "stranger").lower()
    cadence = as_int(fm.get("cadence_days"), DEFAULT_CADENCE) or DEFAULT_CADENCE
    last_touch = parse_date(fm.get("last_touch"))
    days_since = (today - last_touch).days if last_touch else None
    has_trigger = bool((fm.get("trigger") or "").strip())
    trig_date = parse_date(fm.get("trigger_date"))
    trig_age = (today - trig_date).days if trig_date else (0 if has_trigger else None)
    has_warm = as_bool(fm.get("has_warm_path"))
    super_conn = as_bool(fm.get("super_connector"))

    has_relationship = strength in ("strong", "advocate") or status in RELATIONSHIP_STATUSES
    is_dormant = status == "dormant" or (
        strength in ("strong", "advocate") and days_since is not None and days_since > DORMANT_SILENCE_DAYS
    )
    # "due" to reach: never contacted in an active-relationship bucket, or past cadence.
    due = (last_touch is None and has_relationship) or (days_since is not None and days_since >= cadence)

    # Mode router (decides the play; the agent writes the actual strategy).
    if is_dormant:
        mode = "reactivate"
    elif has_relationship:
        mode = "nurture"
    elif has_warm:
        mode = "warm-intro"
    else:
        mode = "cold"

    # Reachability: warm beats cold by ~10-20x, so relationships/paths score high.
    if has_relationship:
        reachability = 100
    elif has_warm:
        reachability = 70
    elif strength == "friendly":
        reachability = 50
    else:
        reachability = 25

    sub = {
        "goal_relevance": CATEGORY_WEIGHT.get(category, 30),
        "fit_value": min(100, 40 + (35 if super_conn else 0) + (25 if category in ("investor", "cofounder") else 0)),
        "reachability": reachability,
        "relationship": STRENGTH_POINTS.get(strength, 0),
        "trigger": round(100 * recency_factor(trig_age)) if has_trigger else 0,
        "dormant_bonus": 100 if is_dormant else 0,
    }
    weights = {
        "goal_relevance": 3.0, "fit_value": 1.5, "reachability": 1.5,
        "relationship": 1.0, "trigger": 2.0, "dormant_bonus": 1.5,
    }
    total = sum(sub[k] * weights[k] for k in sub)

    # Penalties.
    # Status gap: prominent/elite targets are implausible to reach *cold*. A warm
    # path or existing relationship bridges the gap (penalty mostly waived); a
    # specific, mutually-valuable ask softens it (earns the reach).
    status_gap = PROMINENCE_POINTS.get((fm.get("prominence") or "peer").lower(), 0)
    if has_relationship or has_warm:
        status_gap *= 0.2
    elif as_bool(fm.get("specific_ask")):
        status_gap *= 0.4
    total -= 2.0 * status_gap

    if days_since is not None and days_since < cadence:
        # Clamp at 0 so a future/typo'd last_touch caps at the same-day penalty
        # rather than ballooning past 100 (negative days_since → penalty > 100).
        recent = max(0, days_since)
        total -= 2.0 * round(100 * (cadence - recent) / cadence)  # touched recently → ease off
    asks, gives = as_int(fm.get("asks")), as_int(fm.get("gives"))
    if asks > gives:
        total -= 1.0 * min(100, (asks - gives) * 20)  # relational, not transactional

    total += as_int(fm.get("priority_override"))

    return {
        "total": round(total, 1), "sub": sub, "mode": mode, "due": due,
        "category": category, "strength": strength,
        "channel": (fm.get("primary_channel") or "—"),
        "company": (fm.get("company") or "—"),
        "goal_served": (fm.get("goal_served") or "—"),
        "has_trigger": has_trigger,
    }


def display_name(fm, fpath):
    return fm.get("name") or fpath.stem.replace("-", " ").title()


def main():
    ap = argparse.ArgumentParser(description="Rank people by strategic outreach priority")
    ap.add_argument("--dir", default=DEFAULT_DIR, help=f"people directory (default {DEFAULT_DIR})")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"ranking output file (default {DEFAULT_OUT})")
    args = ap.parse_args()

    today = dt.date.today()
    people_dir = Path(args.dir)
    if not people_dir.exists():
        print(f"No people directory at {people_dir} yet — nothing to rank.")
        sys.exit(0)

    rows = []
    for fpath in sorted(people_dir.glob("**/*.md")):
        if fpath.name in ("AGENTS.md", "README.md", "EXAMPLE.md"):
            continue
        status = fpath.parent.name if fpath.parent != people_dir else "prospects"
        fm = parse_frontmatter(fpath.read_text(encoding="utf-8"))
        if not fm:
            continue
        r = score_person(fm, status, today)
        r["name"] = display_name(fm, fpath)
        r["status"] = status
        rows.append(r)

    if not rows:
        print("No people found to rank.")
        sys.exit(0)

    rows.sort(key=lambda r: r["total"], reverse=True)

    out = []
    out.append(f"# Prospects — who to move toward now (ranked {today.isoformat()})")
    out.append("")
    out.append("| Rank | Person | Category | Company | Strength | Mode | Channel | Trigger | Due | Goal serves | Score |")
    out.append("|------|--------|----------|---------|----------|------|---------|---------|-----|-------------|-------|")
    for i, r in enumerate(rows, 1):
        medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else ""
        goal = r["goal_served"]
        goal = goal[:24] + "…" if len(goal) > 25 else goal
        out.append(
            f"| {medal}{i} | {r['name']} | {r['category']} | {r['company']} | {r['strength']} | "
            f"{r['mode']} | {r['channel']} | {'✓' if r['has_trigger'] else '—'} | "
            f"{'✓' if r['due'] else '—'} | {goal} | **{r['total']}** |"
        )
    out.append("")
    out.append("_Mode_: `cold` (no path — needs an undeniable hook), `warm-intro` (1–2 hop path — "
               "default for high-value targets), `nurture` (active tie — give-first, cadence-driven), "
               "`reactivate` (dormant high-ROI reconnection). _Due_ ✓ = past its reconnect cadence.")
    output = "\n".join(out)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Path(args.out).write_text(output + "\n", encoding="utf-8")
    print(output)
    print(f"\nRanking written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
