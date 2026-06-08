# People

The relationship graph the `prospector` skill traverses — who to move toward,
strategically, in service of the goals in `goals/goals.md`. One file per person.

Follows the vault's resource convention (see top-level `AGENTS.md`): flat
resource folder, status-bucket subfolders, files directly inside, frontmatter is
the source of truth. The agent never advances a person between buckets on its
own — the user owns lifecycle transitions (same rule as careerbot).

## Status buckets

- `prospects/` — identified targets, not yet contacted.
- `reaching-out/` — outreach drafted/sent, awaiting a reply.
- `in-conversation/` — active back-and-forth.
- `nurturing/` — an established tie to keep warm (give-first, cadence-driven).
- `dormant/` — once-close, gone quiet → reactivation candidates (highest ROI).
- `not-now/` — explicitly deprioritized.

## Filenames

`<person-slug>.md` (e.g. `jane-doe.md`). Self-describing; the slug is the person.

## Frontmatter (source of truth; the ranking script reads these flat scalars)

```yaml
name: "Jane Doe"
category: investor          # cofounder|investor|customer|connector|mentor|recruiter|peer|operator|other
relationship_strength: friendly   # stranger|friendly|strong|advocate
company: "Acme Ventures"
location: "San Francisco"
primary_channel: linkedin   # email|linkedin|x|... (where they're actually receptive)
has_warm_path: true         # a 1–2 hop intro path exists (slugs/details in the body)
super_connector: false      # bridges clusters the user can't otherwise reach
prominence: prominent       # peer|notable|prominent|elite — their stature/reach vs. the operator
specific_ask: false         # a concrete, mutually-valuable reason that earns a big-status reach
last_touch: 2026-05-01      # empty/absent = never contacted
cadence_days: 30            # tier reconnect rhythm
trigger: "Raised Series A for dev-tools fund"   # an active reason to reach now (empty if none)
trigger_date: 2026-06-01
gives: 1                    # give-first ledger
asks: 0
goal_served: "5y founder — investor relationship"
priority_override: 0        # added to the score; pin (+) or bury (−) someone
```

Structured detail (intro-path slugs, channel handles, history, the drafted
message) lives in the **body**, not frontmatter.

## Privacy

Person files are `*.md` and therefore covered by the vault `.gitignore` — they
stay **local on the volume and never sync out**. Only this `AGENTS.md` syncs.
Keep it that way; this folder holds sensitive notes about real people.
