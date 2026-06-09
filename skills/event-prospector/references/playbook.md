# Event-prospector playbook — encodable heuristics

The research-backed craft behind the skill. Read this before ranking and
planning. Citations illustrative.

## Core stance

Events are a **cold→warm conversion engine** for the relationship graph, not a
calendar of things to learn. "Optimize for access, not sessions" — the hallway,
the dinners, and the side events beat the main stage. An event is worth the time
mainly for **who you'll be in a room with** and whether you can turn that into
warm relationships. The skill *drafts and plans* — it never registers, pays, or
sends on the operator's behalf.

## Location & cost come from memory, never hard-coded

The operator's home base, travel tolerance, and budget are **read from memory at
runtime** (see SKILL.md) — they are not constants in this skill. Everything
location-dependent is distilled by the agent into per-event fields the ranking
script consumes (`travel_tier`, `est_cost_usd`, `budget_fit`), so the skill works
wherever the operator lives or travels and adapts the instant their location
changes. If the location in memory is stale or ambiguous, confirm it and update
memory before scoring travel.

## The scoring rubric (Scouty 5-factor, graph-aware)

Base rubric: score Attendee Quality, Learning, Business Opportunity, Cost
Efficiency, Uniqueness — but the differentiator is to **replace subjective
"Attendee Quality" with a computed who's-going density**:

- Count the overlap of confirmed/expected **attendees + speakers** with (a) the
  operator's **existing relationship graph** (`people/` — warm nodes to deepen)
  and (b) the **target companies / target-person shortlist** (cold nodes to
  convert). Weight ICP-matching targets far above raw headcount.
- **30% relevance gate (Sesamers):** if you don't recognize ≥30% of the names as
  relevant, drop the event a tier.
- **No obtainable attendee list ⇒ you're flying blind** — penalize; you can't
  verify the room.

Founder/VC biases to bake into the soft scores:
- **Curated dinners crush open networking** (~80% follow-up vs ~3%). Events with
  (or near) small curated dinners/side events score far higher. Hosting your own
  dinner is a status play and a give-first lever — flag it as an option.
- **Co-locate on anchors:** the best side events cluster around tentpoles. Score
  the satellites (often > the main stage), and bundle nearby side events/dinners
  into one trip to amortize travel.
- **Stage bias:** early/pre-raise → local meetups (weekly, ~free); growth →
  niche industry events (quarterly, $1–3K); scale/fundraising → mega conferences
  ($2–8K). Match the operator's current stage from goals.

## ROI / cost model (a tiebreaker, not false precision)

```
TrueCost = ticket + travel + lodging + meals + (hours_total × hourly_value)
Value    = Σ expected_valuable_connections × value_per_connection
           + business_pipeline_value + learning_value
Net      = Value − TrueCost
```
Seed estimates: local meetup ≈ free–$50; domestic tech conf all-in ≈ $4–8K;
international ≈ $7–15K. B2B event ROI is real (~4:1 within 18 months) **only if
you follow up** — so weight follow-up potential, not just the day-of.

## Virtual vs. in-person

Virtual = near-zero cost/time (high cost-efficiency) but the relationship-
conversion engine **collapses online** (who's-going density and hallway value go
to near-zero). Route by goal: **in-person for networking/conversion; virtual is
fine for learning/scouting.** The script already collapses `who_density` and
`follow_up_potential` for virtual events.

## How to run a search (tooling)

Use the runtime's **web search tool** — Hermes' built-in `web` tool (Firecrawl-
backed) on the deployed agent, or `WebSearch`/`WebFetch` on a Claude runtime.
**Never shell out to `curl` against DuckDuckGo/Brave HTML** as a search engine:
it gets captcha'd and consent-gated and was the original cause of empty
discovery passes. `WebFetch`/Firecrawl scrape is fine for pulling a *specific*
known page (a Luma event, a demo-day page) into structured data.

## Discovery sources (tiered; query each by topic + geo + date + format)

- **Luma (lu.ma)** — default for AI/tech/startup meetups, demo days, curated
  dinners, side events (discover / city / topic pages). Prefer Luma's
  **JSON/API endpoints** for city/topic discovery over scraping the HTML
  `discover` page — the HTML page **auto-geolocates to the server's IP** (e.g. it
  returned Tokyo results from a cloud VM), so always pass the **memory-resolved
  city explicitly** rather than trusting the default geolocation.
- **Confs.tech** — free JSON API; curated dev conferences + open CFPs, filterable
  by topic.
- **dev.events / developers.events**, **10times.com** — broad conference
  directories (filter city/industry/date/keyword).
- **Eventbrite + Meetup** — local meetups/workshops.
- **LinkedIn Events** — the key unlock for *who's going*: registering "attending"
  exposes the attendee list and creates shared context for pre-event DMs.
- **Company event pages / accelerator demo days (YC, Techstars) / university** —
  highest-intent, target-company-specific. Watch target-company event/news pages;
  Crunchbase shows where target VCs are speaking.
- **X/Twitter** — earliest signal for unannounced side events/dinners; monitor
  target people + event hashtags.

Normalize everything into one record: `{title, date, location, format, url,
topics, organizer, speakers[], attendees[], price, source}`.

## Fallback discovery mode (when web search is down)

Discovery must never return an empty list just because search failed. Degrade
gracefully:

1. **Fast path — live search.** Run the web search tool against the tiered
   sources above. Keep individual lookups short; don't let one stall the pass.
2. **If search is unavailable or 2+ queries come back empty** (tool not
   configured, rate-limited, captcha'd HTML, geolocation noise) → **pivot to
   knowledge-based discovery.** The model has a reasonable working knowledge of
   the major conference calendar (NeurIPS, ICML, AI Engineer Summit, ICLR,
   Strange Loop, RustConf, All Things Open, YC Demo Day, accelerator demo days,
   the main AI-safety convenings, etc.). Cross-reference that against the
   operator's **goals + target companies** to seed a well-curated baseline set.
   **This is explicitly acceptable** — a curated knowledge-based list beats an
   empty one.
3. **Flag knowledge-sourced events** (`unverified: true` in frontmatter) so the
   operator knows their dates/venues are from training knowledge and need
   confirmation before acting. Verify them with a targeted `WebFetch`/scrape of
   the official page once search recovers.

## Virtual / hybrid pass

For an operator in a non-hub city, virtual events are the lowest-cost path to
"being in the room" for **learning/scouting** (not networking — the conversion
engine collapses online, see below). Run a **dedicated pass** with queries that
include `virtual` / `online` / `webinar` / `remote` for the operator's AI-safety
and dev-tools topics. Surface them as options even though the ranking script
correctly ranks them below in-person for networking.

## Networking cadence (before / during / after) — feeds the people graph

**Before (highest leverage):**
- Build a **~20-person target shortlist** from the attendee/speaker list, scored
  by graph-overlap + ICP fit. (Hand these to the `prospector` skill.)
- Verify the attendee list ~90 days out; **send pre-event outreach ~1 week
  ahead**: register "attending" the same LinkedIn Event as a target, then DM —
  shared context lifts reply odds. Pattern: *re-anchor shared context → one
  specific reason → single easy ask ("worth grabbing 15 min Tue?").*
- Warm up speakers by engaging their posts about the event beforehand.

**During:**
- Work the hallway/breakfasts/self-organized dinners. Goal-gate the day: ~3 great
  conversations, not 50 cards. **Book the follow-up before leaving the
  conversation.** Capture name + company + topic + next action within 30 seconds.

**After (where ROI is actually made):**
- **Follow up within 24h** (warm same-day contacts reply ~20–35%; <24–48h convert
  ~60% better than after a week).
- Cadence **Day 1 / 3 / 7 / 14** — each touch re-anchors + adds one new piece of
  value + one easy CTA; never "just checking in." Log everyone into the `people/`
  graph immediately — this is the cold→warm state transition.

## Hand-off to the people graph

Every target met (or to-be-met) at an event is a node for the `prospector`
skill's `people/` graph: pre-event reaches are warm-intro/cold drafts; attending
flips a cold target toward warm; post-event follow-ups run the cadence above.
Keep the two skills in sync — events are how the operator *moves toward* people
who are otherwise cold.
