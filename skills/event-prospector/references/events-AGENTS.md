# Events

The events the `event-prospector` skill discovers, ranks, and plans — where to
show up to advance the goals in `goals/goals.md` and convert cold targets in the
`people/` graph into warm relationships. One file per event.

Follows the vault's resource convention (see top-level `AGENTS.md`): flat
resource folder, status-bucket subfolders, files directly inside, frontmatter is
the source of truth. The agent never advances an event between buckets on its own
and never registers/pays — the operator owns those decisions (same discipline as
careerbot/prospector).

## Status buckets

- `prospects/` — discovered, not yet evaluated.
- `considering/` — under evaluation / on the shortlist.
- `registered/` — the operator has committed to attending.
- `attended/` — past; carries the who-I-met log + follow-up cadence state.
- `passed/` — decided not to attend (with the reason).

## Filenames

`<event-slug>.md`, e.g. `ai-eng-summit-2026-sf.md`. Self-describing.

## Frontmatter (source of truth; the ranking script reads these flat scalars)

```yaml
name: "AI Engineer Summit 2026"
date: 2026-09-15
end_date: 2026-09-17
location: "San Francisco"      # city/region, or "virtual"
format: in-person              # in-person | virtual | hybrid
travel_tier: regional          # local | regional | far — DERIVED from the operator's
                               # memory location + travel tolerance; never hard-coded
est_cost_usd: 5000             # TrueCost: ticket + travel + lodging + meals + time
budget_fit: true               # within the operator's budget (agent's assessment)
calendar_conflict: false       # collides with an existing commitment
attendee_list: true            # can the who's-going list actually be obtained?
target_density: 6              # # of people/-graph + target-company people expected
relevance_pct: 55              # % of recognizable names relevant to the operator (30% gate)
goal_fit: high                 # low | med | high
business_opportunity: high     # low | med | high — revenue/investment/partnership path
learning_value: med            # low | med | high
uniqueness: high               # low | med | high — one-time co-location vs. monthly recurring
has_side_dinners: true         # curated dinners / strong side events attached or nearby
goal_served: "5y founder — investor + customer access"
priority_override: 0           # added to the score; pin (+) or bury (−)
unverified: false              # true ⇒ sourced from model knowledge, not live search —
                               # dates/venue need confirming (report flags it). Optional.
url: "https://…"
organizer: "…"
```

Speaker/attendee target shortlists, the day-of plan, pre-event outreach drafts,
and the post-event who-I-met + follow-up log live in the **body**.

## Privacy

Event files are `*.md` and covered by the vault `.gitignore` — they stay **local
on the volume and never sync out**. Only this `AGENTS.md` syncs.
