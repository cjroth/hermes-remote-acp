---
name: event-prospector
description: "Maintain an always-fresh, ranked shortlist of the events worth showing up for — conferences, meetups, demo days, hackathons, summits, curated dinners — chosen to advance the operator's goals and convert cold targets in their relationship graph into warm ones. Scores events mostly by WHO will be there (overlap with the people/ graph + target companies), plus goal-fit, cost/travel, timing, and follow-up potential; then plans the top picks (who to meet, pre-event outreach to book meetings, the day-of and follow-up cadence). Reads the operator's location/travel/budget from MEMORY — never hard-codes a city. Drafts and plans only; never registers, pays, or sends. Use when asked which events to attend, to refresh the event ranking, or on a schedule."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Events, Conferences, Networking, Prospecting, Travel, Relationships]
---

# Event-prospector — where to show up, and how to work it

Keep an always-up-to-date, ranked shortlist of the **events** worth the
operator's time, chosen to grow their network in a strategic direction and turn
cold targets into warm relationships. For each top pick, plan it: **who to meet,
the pre-event outreach to book those meetings, the day-of plan, and the follow-up
cadence.**

Events are a **cold→warm conversion engine** for the relationship graph, not a
calendar of talks. Optimize for *access*, not sessions — the hallway, the side
events, and the dinners beat the main stage. An event earns a spot mainly by
**who you'll be in a room with** and whether you can convert that into
relationships. This is the sibling of the `prospector` skill: events are how the
operator *moves toward* people who are otherwise cold.

**Read [`references/playbook.md`](references/playbook.md) before ranking or
planning** — it holds the encodable craft (the graph-aware Scouty rubric, the
30%-relevance gate, the curated-dinner heuristic, the tiered discovery sources,
the ROI/cost model, virtual-vs-in-person routing, and the before/during/after
networking cadence). This skill is the workflow; the playbook is the craft.

**Hard rules: drafts and plans only.** Never register, buy a ticket, book travel,
or send a message on the operator's behalf — surface the plan and the drafts for
them to act on (like careerbot never submits and prospector never sends). Never
advance an event between status buckets; the operator owns those decisions.

Channel-agnostic: speak in the conversation; for a no-reply digest run you may
hand the report to the `email-me` skill. **When delivering via email, the
`email-me` markdown renderer supports pipe-delimited tables** — but if you're
unsure, simplify the ranked table to <6 columns (Rank, Event, When, Travel,
Cost, Verdict) so it renders cleanly in narrow email viewports.

## 1. Load context — and get location from MEMORY

Ground every recommendation. In particular, **the operator's location, travel
tolerance, and budget are read from memory at runtime — never hard-coded.** A
city baked into the skill would be wrong: the operator may move (memory notes a
possible relocation), so resolve it fresh every run.

- **Location & logistics from memory.** Read the operator's **current location,
  travel tolerance, and budget** from their memory (`memories/USER.md` and
  `memories/MEMORY.md`), with `context/preferences.md` (its **Location** section
  and travel tolerance) as the richer fallback. Use that resolved location +
  travel tolerance + budget to derive each event's `travel_tier` /
  `est_cost_usd` / `budget_fit`. Do not write a city into any file as a constant
  — it's always a function of current memory.
  - **If the location is missing, stale, or ambiguous** (e.g. memory says a move
    "may be complete or paused"), branch on whether anyone's there to answer:
    - **Interactive run:** **ask the operator to confirm where they're based now
      (and any planned trips), then update memory** before scoring travel.
    - **Cron / no-reply digest run (nobody to ask):** **do not block or guess
      silently.** Proceed with the **last-known** location, but (a) put a
      prominent **"⚠️ Location needs confirmation"** callout in the report header,
      (b) if memory *implies* a likely new base (e.g. an in-progress move to a
      named city), score events against **both** the last-known and the
      most-likely-new location and show both, and (c) ask the operator to confirm
      next time they're in the loop.
  - To detect drift automatically, treat a `location_staleness_days` field in
    memory (days since the location was last confirmed) as the trigger: past a
    threshold, flag the location as stale per the above even if it looks set.
- `goals/goals.md` — the strategic direction and current stage (events are scored
  against goals; stage biases which event *formats* win — see playbook).
- `people/**` and `companies/`, `roles/`, `context/` — the relationship graph and
  target companies. These drive the **who's-going density** score: who from the
  graph or the target shortlist will be in the room.
- `events/**` — events already tracked. Read `events/AGENTS.md` for the schema.
- **Calendar (read-only), if available** — check for conflicts via the `proton`
  skill's CalDAV or a calendar MCP. Never modify the calendar; just detect
  collisions to set `calendar_conflict`.

If there's no `events/` folder yet, create it and seed `events/AGENTS.md` from
[`references/events-AGENTS.md`](references/events-AGENTS.md).

## 2. Discover events

Find events relevant to the goals + the resolved location/trips, working the
tiered sources in the playbook (Luma, Confs.tech API, dev.events, 10times,
Eventbrite/Meetup, **LinkedIn Events** for attendee lists, company/accelerator
demo-day pages, X). Filter on: topic/industry (from goals + preferences), format,
date window, **geo radius from the memory-resolved location (and any planned
trips)**, and whether an attendee/speaker list is obtainable. **Co-locate on
anchors** — query side events/dinners clustered around tentpole events; the
satellites often beat the main stage.

**How to search (and what to do when search is down).** Use the runtime's web
search tool — Hermes' built-in `web` tool (Firecrawl) on the deployed agent, or
the `WebSearch`/`WebFetch` tools on a Claude runtime. **Do not shell out to
`curl` against DuckDuckGo/Brave HTML** — that gets captcha'd and consent-gated.
The search craft and a **fallback discovery mode** for when web search is
unavailable live in the playbook ("Discovery sources" + "Fallback discovery
mode") — read them. In short: try live search first; if it's down or empty,
**pivot to knowledge-based discovery** (the model's working knowledge of the
major conference calendar, cross-referenced to the operator's goals and target
companies) rather than returning an empty list — and **mark those events as
knowledge-sourced (`unverified: true`)** so the operator knows to confirm
dates/venues. A well-curated knowledge-based list beats no list.

**Run a dedicated virtual/hybrid pass.** For an operator in a non-hub city,
virtual events are the lowest-cost path to "being in the room" for the
learning/scouting use case. Explicitly query for `virtual` / `online` /
`webinar` / `remote` AI-safety and dev-tools summits and workshops, not just
in-person events. (The ranking script correctly collapses who's-going density
for virtual — they'll rank below in-person for *networking* — but the operator
should still see them as options.)

For each event, compute **who's-going density**: cross-reference the
attendee/speaker list against `people/` and the target companies/shortlist, and
apply the **30% relevance gate**. Then write `events/<status>/<slug>.md` with the
frontmatter from `events/AGENTS.md` — setting `travel_tier`/`est_cost_usd`/
`budget_fit` from the memory-resolved location, and `target_density`/
`relevance_pct` from the graph overlap. New finds go in `prospects/`. Put the
speaker/attendee target shortlist, day-of ideas, and reasoning in the **body**.

**Quality gate:** only add events that plausibly serve a goal *and* clear the
relevance gate. Don't pad the list with generic events.

**Search efficiently — a floor on events is not a floor on searches.** Reaching
50+ events does *not* mean dozens of searches. Lean on **list-yielding sources**
that return many events per call — Confs.tech's JSON API, Luma city/topic JSON,
the 10times/dev.events directory pages — so a handful of queries seeds most of
the list; reserve one-off lookups for specific high-value anchors. The expensive
part is **per-event attendee/speaker lookups**: don't fetch a full attendee list
for all 50. Estimate who's-going density from the event's topic, host, and
audience for the long tail, and spend real attendee-list lookups only on the
shortlist you'll actually plan in §4 (the top ~5, plus any near the attend bar).
Fold the virtual/hybrid pass in as a couple of added queries, not a second full
sweep. When live search is down, knowledge-based discovery (below) costs zero
searches — use it rather than burning retries.

## 3. Rank

```bash
python3 scripts/rank-events.py
```

Reads every `events/**/*.md`, applies the hard-constraint penalties (calendar
conflict, over budget, far-travel-for-a-thin-room, <30% relevant, date passed)
and the soft-score rubric (who's-going density weighted highest, then goal-fit,
business opportunity, uniqueness, follow-up potential, cost-efficiency, learning),
and writes the ranked table to `/data/vault/events.md` (also stdout). **Always
run it** — verdicts drift with the calendar alone (events approach, then pass).

The script reports **strategic value (the score) and accessibility (the Travel
column) as two separate dimensions**, so a high-value event that needs a flight
reads as exactly that — a `far` event clearing the attend bar is labelled **✈️
attend (travel)**, distinct from a local **✅ attend**. It also adds a
**co-location bonus**: events sharing a city within ±4 weeks get a bundle bonus
and a 🧳 marker, surfacing "hit 3 things on one trip" as a ranking signal. Use
that signal in the bundling section of the report.

## 4. Plan the top picks (rank-then-commit)

Surface a **shortlist of ~3–5** with pros/cons before planning deeply — don't
auto-plan only the top hit. For each, apply the playbook and produce:

- **Why go** — the specific goal it serves and the concrete pre-registration aim
  (e.g. "meet 3 dev-tools investors I've been trying to reach"), not "visibility."
- **Who to meet** — a target shortlist (~up to 20) pulled from the who's-going
  overlap with `people/` + target companies, prioritized by graph value and ICP
  fit. These are nodes for the `prospector` graph.
- **Pre-event outreach** — drafts to book meetings ~1 week out (the "I'll be at
  X, worth grabbing 15 min?" pattern; register "attending" the same LinkedIn
  Event first for shared context). Honor `prospector`'s message rules and the
  status gap. Flag speakers to warm up by engaging their posts beforehand.
- **Side events & dinners** — surface curated dinners/satellites (or propose the
  operator *host* one — the give-first status play); these carry the follow-up.
- **Logistics** — travel feasibility against the resolved location and calendar,
  a rough TrueCost, and (for far events) a co-located bundle of nearby events to
  amortize the trip.
- **Follow-up plan** — the Day-1/3/7/14 cadence to run afterward, handed to the
  `prospector` graph as the cold→warm conversion.

Get strategic: which event puts the operator in a room they otherwise couldn't
reach, and who does showing up there make reachable next?

## 5. Persist & report

- Update event files (density, flags, plans, and — after the operator attends —
  the who-I-met log + follow-up state). Re-run `rank-events.py` if anything
  material changed so `events.md` is current.
- **Report in this order — lead with the verdict, don't bury it behind a location
  disclaimer:**
  1. **One-sentence strategic verdict** — the most important thing first
     ("Your goals need SF/Vancouver rooms; here's the best path to them").
  2. **Ranked table** (the data, from `events.md`).
  3. **Top-pick deep dives** (the narrative: each pick's why, who-to-meet,
     pre-event drafts, logistics).
  4. **Location / strategic-tension callout** — *surfaced as a finding, not a
     disclaimer at the top* (see the rule below). Include the **"⚠️ Location
     needs confirmation"** flag here on cron runs with stale location.
  5. **Bundling strategy** — use the script's 🧳 co-location signal to propose
     amortizing far trips ("one SF trip hits these three").
  6. **Virtual alternatives** — the lower-cost learning/scouting options from the
     virtual pass.
  Call out **curated dinners / host-your-own** opportunities and any **flagged**
  events (conflict/over-budget/thin) within the relevant section, and **mark
  knowledge-sourced events** (`unverified`) as needing date/venue confirmation.
  Mention `events.md` was written.
- **Strategic-finding rule (don't frame travel as a flaw in the picks).** When
  **≥50% of the recommended events are `far` or `regional`**, open the
  location/tension callout (step 4) as a **strategic finding**, not an apology:
  - Name the gap — *the operator's goals require rooms that don't exist in their
    current city*; travel is the **price of the current location**, not a defect
    in the recommendations.
  - Tie it to any **location/move goal** in `goals.md` — this is concrete
    evidence for (or against) a relocation, and frame it that way.
  - Propose **bundling trips** to amortize the travel (feed from the 🧳 signal).
  The scoring already penalizes `far` via cost-efficiency; this step connects
  that penalty back to the operator's goals so it reads as insight, not an
  excuse.
- **Gently coach, don't overrule** (same spirit as `goals`/`prospector`): if the
  operator wants to travel far for a thin room, or attend a virtual event hoping
  to network, say so and propose the better move — then defer to their call.

## Hard rules

- **Plan and draft only — never register, pay, book travel, or send.** Every
  action stays with the operator.
- **Never advance an event between status buckets** on the operator's behalf.
- **Location/budget always from memory** — never hard-code a city; re-resolve
  each run and confirm + update memory if stale.
- **Quality-gate every addition** — must serve a goal and clear the relevance gate.
- **Target at least 50 events in the shortlist**, aiming for a ~50/50 mix of
  local (RTP) and travel (far/regional) events. The operator wants breadth —
  more options to choose from, not a pruned top-5.
- **Privacy:** event files are `*.md` and stay local (vault `.gitignore`); never
  push them or surface them outside the operator's own channels. Only `AGENTS.md`
  syncs.
- **Be honest in the report** — if a pass found nothing worth attending, say so
  rather than padding the list.
