#!/usr/bin/env python3
"""Rank the events in the vault by which are most worth the operator's time *now*.

The deterministic counterpart to the event-prospector skill's reasoning — the
sibling of `rank-people.py`. The agent maintains one markdown file per event
under `events/<status>/<slug>.md` with structured frontmatter; this script reads
it, applies hard-constraint penalties and a soft-score rubric, and writes a
ranked table to `events.md` at the vault root (and stdout). Run it every pass.
Stdlib only.

LOCATION IS NEVER HARD-CODED. The script knows nothing about cities. The agent
reads the operator's current location + travel tolerance from their *memory*
(see SKILL.md) and distills it into a per-event `travel_tier`
(local|regional|far) and `est_cost_usd`/`budget_fit`. The script only consumes
those derived fields, so the skill works wherever the operator lives or is
traveling, and adapts the moment their memory's location changes.

Scoring model (encodes the research — see references/playbook.md). Soft scores
are 0–100 before weighting; "who's-going density" dominates, per the founder/VC
heuristic that the hallway (who you meet) beats the main stage:

    score =
        3.0 * who_density          # overlap with the people/ graph + target companies
      + 2.0 * goal_fit             # serves a current goal
      + 1.5 * business_opportunity # revenue / investment / partnership path
      + 1.5 * uniqueness           # one-time co-location vs. a monthly recurring meetup
      + 1.5 * follow_up_potential  # curated dinner / side event (~80% vs ~3% follow-up)
      + 1.5 * cost_efficiency      # value vs. TrueCost (travel + time); virtual is cheap
      + 1.0 * learning_value
      − hard-constraint penalties (calendar conflict, over budget, far-for-thin, <30% relevant)
      + co_location_bonus          # +30 per co-located event (same city, ±4 wks) — trip amortization
      + priority_override

The `total` is the event's STRATEGIC VALUE; ACCESSIBILITY (local|regional|far|
virtual) is reported as a separate dimension (the Travel column) so a high-value
event that happens to need a flight reads as exactly that — not as "skip" and
not as the same ✅ as a local must-go. The verdict is travel-aware: a far event
that clears the attend bar is labelled "✈️ attend (travel)", distinguishing
"worth the trip" from a local "✅ attend".

Frontmatter the script reads (everything else lives in the body):
    date / end_date        YYYY-MM-DD
    location               city / region, or "virtual"
    format                 in-person | virtual | hybrid
    travel_tier            local | regional | far   (AGENT-DERIVED from memory location)
    est_cost_usd           int      (TrueCost estimate: ticket + travel + lodging + time)
    budget_fit             true|false   (within the operator's budget — agent's call)
    calendar_conflict      true|false   (collides with an existing commitment)
    attendee_list          true|false   (can the who's-going list actually be obtained?)
    target_density         int      (# of people/-graph + target-company people expected)
    relevance_pct          int      (% of recognizable names relevant to the operator; 30% gate)
    goal_fit / business_opportunity / learning_value / uniqueness   low|med|high
    has_side_dinners       true|false   (curated dinners / strong side events attached)
    goal_served            free text (display)
    priority_override      int

Status comes from the parent folder name.

Usage:
    rank-events.py [--dir /data/vault/events] [--out /data/vault/events.md]
"""
import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

DEFAULT_DIR = os.environ.get("EVENTS_DIR", "/data/vault/events")
DEFAULT_OUT = os.environ.get("EVENTS_OUT", "/data/vault/events.md")

TIER = {"low": 33, "med": 66, "medium": 66, "high": 100}
TRAVEL_COST_EFFICIENCY = {"local": 100, "regional": 60, "far": 30}
RELEVANCE_GATE_PCT = 30  # "if <30% of names are relevant, drop it a tier" (Sesamers)


def parse_frontmatter(text):
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


def as_bool(v, default=False):
    s = str(v).strip().lower()
    if s in ("true", "yes", "1"):
        return True
    if s in ("false", "no", "0"):
        return False
    return default


def as_int(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def tier(v):
    return TIER.get((v or "").strip().lower(), 0)


def parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def score_event(fm, status, today):
    fmt = (fm.get("format") or "in-person").lower()
    travel = (fm.get("travel_tier") or "").lower()
    density = as_int(fm.get("target_density"))
    attendee_list = as_bool(fm.get("attendee_list"), default=False)
    is_virtual = fmt == "virtual"

    # Who's-going density — the differentiator. Capped low if the list is
    # unobtainable (can't verify who's there), and collapsed for virtual
    # (hallway/relationship conversion barely happens online).
    who = min(100, density * 20)
    if not attendee_list:
        who = min(who, 40)
    if is_virtual:
        who = round(who * 0.3)

    if is_virtual:
        cost_eff = 95  # near-zero cost/time
    else:
        cost_eff = TRAVEL_COST_EFFICIENCY.get(travel, 50)

    if as_bool(fm.get("has_side_dinners")):
        follow_up = 100  # curated dinners ≈ 80% follow-up vs ~3% open networking
    elif is_virtual:
        follow_up = 15
    else:
        follow_up = 50

    sub = {
        "who_density": who,
        "goal_fit": tier(fm.get("goal_fit")),
        "business_opportunity": tier(fm.get("business_opportunity")),
        "uniqueness": tier(fm.get("uniqueness")),
        "follow_up_potential": follow_up,
        "cost_efficiency": cost_eff,
        "learning_value": tier(fm.get("learning_value")),
    }
    weights = {
        "who_density": 3.0, "goal_fit": 2.0, "business_opportunity": 1.5,
        "uniqueness": 1.5, "follow_up_potential": 1.5, "cost_efficiency": 1.5,
        "learning_value": 1.0,
    }
    total = sum(sub[k] * weights[k] for k in sub)

    # Hard-constraint penalties (don't silently drop — surface them, ranked low).
    flags = []
    if as_bool(fm.get("calendar_conflict")):
        total -= 150
        flags.append("calendar conflict")
    if not as_bool(fm.get("budget_fit"), default=True):
        total -= 100
        flags.append("over budget")
    if travel == "far" and density < 2:
        total -= 100
        flags.append("far travel for thin who's-going")
    rel = fm.get("relevance_pct")
    if rel != "" and rel is not None and as_int(rel, 100) < RELEVANCE_GATE_PCT:
        total -= 60
        flags.append("<30% relevant")
    if not attendee_list:
        total -= 20  # uncertainty: who's-going can't be verified

    total += as_int(fm.get("priority_override"))

    # A past event that isn't in the attended bucket is noise — sink it and force
    # a skip verdict regardless of how good it looked.
    event_date = parse_date(fm.get("date"))
    passed = event_date and event_date < today and status != "attended"
    if passed:
        total -= 500
        flags.append("date passed")

    # Verdict is derived in main() AFTER the co-location bonus is applied, so a
    # bundle-able event isn't judged on its pre-bundle score.
    return {
        "total": round(total, 1), "sub": sub, "passed": passed, "flags": flags,
        "format": fmt, "travel": travel or "—", "is_virtual": is_virtual,
        "location": fm.get("location") or "—", "density": density,
        "est_cost": as_int(fm.get("est_cost_usd")),
        "goal_served": fm.get("goal_served") or "—",
        "date": event_date, "co_located": 0,
    }


def derive_verdict(total, passed, travel):
    """Strategic-value → verdict, but travel-aware so far events read distinctly.

    A far event clearing the attend bar is "worth the trip", not the same call as
    a local must-go — surface that rather than stamping ✅ on everything ≥700.
    """
    if passed or total < 400:
        return "⏭ skip"
    if total >= 700:
        return "✈️ attend (travel)" if travel == "far" else "✅ attend"
    return "🤔 evaluate"


CO_LOCATION_WINDOW_DAYS = 28  # ±4 weeks counts as one bundle-able trip
CO_LOCATION_BONUS = 30        # per co-located event, when ≥2 neighbors co-locate


def apply_co_location_bonus(rows):
    """Reward trips you can amortize: for each in-person event, count OTHER
    in-person events in the same city within ±4 weeks. With ≥2 co-located
    neighbors, add +30 each — surfacing "hit 3 things on one trip" as a ranking
    signal, not just narrative commentary. Mutates rows in place."""
    for r in rows:
        city = (r["location"] or "").strip().lower()
        if r["is_virtual"] or not r["date"] or not city or city == "—":
            continue
        n = sum(
            1 for o in rows
            if o is not r and not o["is_virtual"] and o["date"]
            and (o["location"] or "").strip().lower() == city
            and abs((o["date"] - r["date"]).days) <= CO_LOCATION_WINDOW_DAYS
        )
        r["co_located"] = n
        if n >= 2:
            r["total"] = round(r["total"] + CO_LOCATION_BONUS * n, 1)


def when_cell(d, today):
    if not d:
        return "—"
    delta = (d - today).days
    if delta < 0:
        return f"{d.isoformat()} (past)"
    if delta == 0:
        return f"{d.isoformat()} (today)"
    return f"{d.isoformat()} ({delta}d)"


def display_name(fm, fpath):
    return fm.get("name") or fpath.stem.replace("-", " ").title()


def main():
    ap = argparse.ArgumentParser(description="Rank events by strategic value")
    ap.add_argument("--dir", default=DEFAULT_DIR, help=f"events directory (default {DEFAULT_DIR})")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"ranking output file (default {DEFAULT_OUT})")
    args = ap.parse_args()

    today = dt.date.today()
    events_dir = Path(args.dir)
    if not events_dir.exists():
        print(f"No events directory at {events_dir} yet — nothing to rank.")
        sys.exit(0)

    rows = []
    for fpath in sorted(events_dir.glob("**/*.md")):
        if fpath.name in ("AGENTS.md", "README.md", "EXAMPLE.md"):
            continue
        fm = parse_frontmatter(fpath.read_text(encoding="utf-8"))
        if not fm:
            continue
        status = fpath.parent.name if fpath.parent != events_dir else "prospects"
        r = score_event(fm, status, today)
        r["name"] = display_name(fm, fpath)
        r["status"] = status
        rows.append(r)

    if not rows:
        print("No events found to rank.")
        sys.exit(0)

    # Bundle-able trips get a co-location bonus before the verdict is judged…
    apply_co_location_bonus(rows)
    # …then derive each verdict against the final (post-bundle) strategic value.
    for r in rows:
        r["verdict"] = derive_verdict(r["total"], r["passed"], r["travel"])

    rows.sort(key=lambda r: r["total"], reverse=True)

    out = []
    out.append(f"# Events — what's worth showing up for (ranked {today.isoformat()})")
    out.append("")
    out.append("| Rank | Event | When | Where | Format | Travel | Est $ | Targets | Verdict | Goal serves | Score |")
    out.append("|------|-------|------|-------|--------|--------|-------|---------|---------|-------------|-------|")
    for i, r in enumerate(rows, 1):
        medal = "🥇 " if i == 1 else "🥈 " if i == 2 else "🥉 " if i == 3 else ""
        goal = r["goal_served"]
        goal = goal[:22] + "…" if len(goal) > 23 else goal
        cost = f"${r['est_cost']:,}" if r["est_cost"] else "—"
        flagnote = f" ⚠️ {', '.join(r['flags'])}" if r["flags"] else ""
        bundlenote = f" 🧳×{r['co_located']} bundle" if r.get("co_located", 0) >= 2 else ""
        out.append(
            f"| {medal}{i} | {r['name']}{flagnote}{bundlenote} | {when_cell(r['date'], today)} | {r['location']} | "
            f"{r['format']} | {r['travel']} | {cost} | {r['density']} | {r['verdict']} | {goal} | **{r['total']}** |"
        )
    out.append("")
    out.append("_Verdict_: ✅ attend (≥700, local/regional) · ✈️ attend (travel) (≥700 but `far` — "
               "worth the trip, not a local must-go) · 🤔 evaluate (400–699) · ⏭ skip (<400 or passed). "
               "_Score_ = strategic value; _Travel_ = accessibility (local/regional/far/virtual) — read "
               "them as two separate dimensions. _Targets_ = people from the relationship graph / target "
               "companies expected to attend (the who's-going density — the hallway beats the main stage). "
               "🧳×N = N other tracked events co-locate in the same city within ±4 weeks (bundle the trip). "
               "⚠️ flags are hard-constraint hits (calendar conflict, over budget, far travel for a thin "
               "room, <30% relevant, date passed).")
    output = "\n".join(out)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Path(args.out).write_text(output + "\n", encoding="utf-8")
    print(output)
    print(f"\nRanking written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
