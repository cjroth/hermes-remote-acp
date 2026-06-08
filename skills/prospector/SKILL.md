---
name: prospector
description: "Maintain an always-fresh, ranked shortlist of the people the operator should move toward to grow their network in service of their goals — and for each one, the purpose of the conversation, the right medium, the move (cold / warm-intro / nurture / reactivate), and a drafted message ready to send. Treats relationships as a graph to traverse: cold outreach, warm intros via 1–2 hop paths, give-first nurturing, and dormant-tie reactivation. Reads the vault for goals and context; stores a people/ relationship graph and writes a ranked prospects.md. Drafts only — never sends. Use when asked who to reach out to / network with, to refresh the prospect ranking, or on a schedule."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Networking, Prospecting, Outreach, CRM, Relationships, Coaching]
---

# Prospector — who to move toward, and how

Keep an always-up-to-date, ranked shortlist of the **people** worth reaching out
to, chosen to grow the operator's network in a *strategic direction* set by their
goals. For each recommendation, produce the **purpose** of talking to them, the
**medium**, the **move** (cold / warm-intro / nurture / reactivate), and a
**drafted message** ready to review and send.

The asset is the operator's relationship *graph* and its **paths**, not a list of
strangers. Play it like a graph: jump cold only when the value is high and you
bring an undeniable hook; otherwise find a 1–2 hop warm path, or nurture toward
one. Moving in a social direction *opens relationship-paths* toward the targets
that matter — treat intermediaries as sub-goals. Be relational, not transactional:
give before you ask.

**Read [`references/playbook.md`](references/playbook.md) before strategizing or
drafting** — it holds the encodable heuristics (weak ties, structural holes,
two-hop traversal, give-first, dormant-tie reactivation, the trigger→angle table,
channel lookup, the message rules, investor warm-intro protocol, and informational-
interview directness calibration). This skill is the workflow; the playbook is the
craft.

**Hard rule: this skill drafts, it never sends.** No email, DM, or intro goes out
without the operator. Like careerbot never submits, prospector never reaches out
on its own. It also never advances a person between status buckets — the operator
owns lifecycle transitions.

Pipeline: load context → discover/refresh people → `rank-people.py` → strategize
the top picks (purpose, medium, move, message) → report. Channel-agnostic: you
speak in the conversation and the harness routes it; for a no-reply digest run you
may hand the report to the `email-me` skill.

## 1. Load context

Ground every recommendation in who the operator is and where they're going:

- `goals/goals.md` — the strategic direction. This is what "strategic" *means*
  here; every person should serve a goal. (Run the `goals` skill's status check
  if useful.)
- `people/**` — the existing relationship graph (if any). Read `people/AGENTS.md`
  for the schema.
- `companies/`, `roles/`, `applications/`, `context/` — careerbot's data. Target
  companies and roles are **people-bearing**: a company the operator is tracking
  is a place to find a person (a founder to learn from, a hiring manager, a design-
  partner contact). Cross-reference liberally.

If there's no `people/` folder yet, create it and seed `people/AGENTS.md` from
[`references/people-AGENTS.md`](references/people-AGENTS.md).

## 2. Discover / refresh people

Expand and update the graph. Two sources:

1. **From the vault** — people implied by what's already there: founders/leaders
   of tracked companies, hiring managers for roles in `roles/`, anyone named in
   `context/`. Promote them into `people/` with a category and a goal link.
2. **From research** — given the goals + profile, find *new* people worth knowing:
   potential cofounders, investors whose thesis fits (AI dev-tools / agent infra /
   the operator's product thesis), early-customer/design-partner candidates,
   recruiters/hiring managers at target companies, and **super-connectors** who
   bridge into clusters the operator can't currently reach. Use web research
   (WebSearch/WebFetch) to find them and their **triggers** (recent funding, a
   launch, a job change, a post worth engaging). Honor the **avoid list** in
   careerbot's profile — don't prospect people at companies the operator avoids.

**ICP gate:** before creating a file, ask *does reaching this person plausibly
advance a goal?* If not, skip them. Don't pad the graph.

**Build to at least 100.** Keep discovering until **≥100 people remain after the
ICP gate** (across all categories and statuses combined). One pass rarely gets
there — loop: widen categories (cofounders, investors, customers, connectors,
mentors, recruiters, operators, peers), work down the ~80 tracked companies for
people at each, mine new search angles (conference speakers, podcast guests,
authors of relevant work, portfolio lists, GitHub collaborators, mutuals of
people already in the graph), and pull in vault-implied people. The 100 is a
floor on *quality* prospects, not a license to pad — never add someone who fails
the ICP gate just to hit the number. If you genuinely exhaust plausible
candidates before 100, stop and say how many you reached and why.

For each person, write `people/<status>/<slug>.md` with the frontmatter from
`people/AGENTS.md` (category, relationship_strength, channels, `has_warm_path`,
`super_connector`, `prominence`, `specific_ask`, `last_touch`, `cadence_days`,
`trigger`/`trigger_date`, `gives`/`asks`, `goal_served`). Set `prominence`
honestly relative to the operator's *current* standing (an early-stage individual
builder, pre-raise): a peer founder is `peer`; a well-known operator is
`prominent`; an a-list VC or billion-dollar-company CEO is `elite`. New cold finds
go in `prospects/`. Put intro-path
slugs, channel handles, history, and your reasoning in the **body**. Keep
frontmatter scalars accurate — the ranking script reads them.

**Map intro paths.** For valuable-but-cold targets, look for a 1–2 hop path
through people already in the graph; if one exists, set `has_warm_path: true` and
name the path (and its weakest link) in the body. If none exists, note which
reachable intermediary to nurture *toward* this target.

## 3. Rank

```bash
python3 scripts/rank-people.py
```

Reads every `people/**/*.md`, computes the composite `priority_score` (see the
script header and playbook for the model — goal relevance, fit/super-connector,
reachability, relationship strength, recency-decayed triggers, dormant bonus,
minus recent-contact and give/ask-imbalance penalties), and writes a ranked table
to `/data/vault/prospects.md` (also printed to stdout). **Always run it**, even if
the graph is unchanged — the ranking must reflect the latest state (cadences and
trigger recency drift with time alone).

The table's `Mode` and `Due` columns are the script's first cut; you refine the
actual strategy in the next step.

## 4. Strategize the top picks

For the top recommendations (default ~3–5; more on request), apply the playbook
and produce, for each person:

- **Purpose** — the specific, honest goal of the conversation, tied to a goal
  horizon. People don't want to chat without purpose; name it. (And know when the
  purpose is simply *opening a path* — a deliberate move toward a later target.)
- **Move** — `cold` / `warm-intro` / `nurture` / `reactivate` (start from the
  script's `Mode`, then sanity-check it). For warm intros, lay out the path and
  the double-opt-in plan; for cold high-value targets, the undeniable hook; for
  nurture/reactivate, the give to lead with.
- **Respect the status gap.** Reach relative to the operator's standing. Don't
  recommend cold-reaching a `prominent`/`elite` target (a-list VC, billion-dollar-
  company CEO) on a vague "let's connect" — they're drowning in inbound and won't
  bite. Such a reach is only worth recommending when **either** a warm path
  exists (find or build one — route through a reachable intermediary as a sub-
  goal) **or** there's a `specific_ask`: a concrete, mutually-valuable, hard-to-
  ignore reason (e.g. "would you angel-invest in my seed round?", a genuinely
  novel collaboration, a sharp question only they can answer). Absent both, don't
  surface them as an outreach target yet — note the intermediary to nurture toward
  instead, or park them until the operator has the traction/standing to earn the
  reach. The ranking already penalizes cold high-prominence targets; honor that in
  the narrative.
- **Medium** — the channel from the playbook lookup, chosen for where *they're*
  receptive (with the X "engage-before-DM" rule, the LinkedIn-DM default, or the
  intro protocol as applicable).
- **Drafted message** — 2 sentences to 2 short paragraphs, following the message
  rules verbatim (length, personalization test, single low-friction ask,
  you>we, seniority-shortening, trigger→angle). For investors, include the
  **"why this won't waste your time"** framing (lead with the undeniable signal;
  the "not raising yet" relationship play when apt) and, for an intro, the
  <150-word forwardable blurb. For job/career reaches, calibrate directness by
  relationship × status gap and keep informational reaches genuinely informational.

Get genuinely creative and strategic here — this is the 4D chess. Look several
moves ahead: who does reaching this person put within reach next?

## 5. Persist & report

- Update the person files (triggers, `last_touch` when the operator actually
  reaches out, give/ask ledger, path notes). Re-run `rank-people.py` if anything
  material changed so `prospects.md` is current.
- Report one consolidated summary: the ranked top picks with each one's purpose,
  move, medium, and drafted message; note dormant-tie reactivations and any
  "nurture is due" surfaces separately (they're the cheap, high-ROI wins); flag
  valuable targets that are currently unreachable and the intermediary to move
  toward. Mention `prospects.md` was written.
- **Gently coach, don't overrule** (same spirit as the `goals` skill): if the
  operator wants to cold-blast a high-value target where a warm path clearly
  exists, or reach with an ask when the give/ask ledger is lopsided, say so and
  propose the better move — then defer to their call.

## Hard rules

- **Draft only — never send.** No outreach, DM, intro, or email goes out without
  the operator.
- **Never advance a person between status buckets** on the operator's behalf; they
  own the lifecycle.
- **ICP gate every addition** — every person must plausibly serve a goal.
- **Respect the avoid list** in careerbot's profile.
- **Privacy:** person files are `*.md` and stay local (vault `.gitignore`); never
  push them or surface them outside the operator's own channels. Only `AGENTS.md`
  syncs.
- **Be honest in the report** — if a pass found nothing new worth adding, say so
  rather than padding the graph with weak prospects.
