---
name: goals
description: "Set, review, refine, and remember the operator's goals across horizons (5y / 2y / 1y / 6mo / 3mo / 1mo / 1wk), stored in the vault. On first run it elicits goals one horizon at a time; on later runs it reminds the operator of their current goals, coaches them on alignment, and nudges a re-baseline when the goals have gone stale. Acts as a gentle but critical coach — it steers, refines, and pushes back, but never overrules. Use when asked to set/review/update goals, or when run on a schedule (cron) as a recurring check-in."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Goals, Coaching, Planning, Productivity, Personal]
---

# Goals — set, refine, remember, coach

Help the operator set and keep meaningful goals across seven horizons —
**5 years, 2 years, 1 year, 6 months, 3 months, 1 month, 1 week** — and act as a
gentle but honest coach who keeps those goals aligned and alive over time.

The job is **not** to be a passive note-taker. It is to help the operator set
*better* goals than they would alone: actionable, achievable, and laddering up
to what they actually want. Steer, refine, and push back when something feels
off — but the operator always has the final word. Coach, don't overrule.

You speak in the conversation; **delivery is channel-agnostic** — whatever
channel the operator is on, the harness routes your messages there. A run is
just you talking to them and waiting for replies, whether they invoked the skill
or cron did. For a pure no-reply reminder (no questions to answer), you may hand
the finished reminder to the `email-me` skill, the same way the digest skills do.

## 0. Read the state

```bash
python3 scripts/goals.py status
```

This prints JSON describing the goals file (default `/data/vault/goals/goals.md`):

- `exists` — whether goals have been set yet.
- `today` — the current date (use this when stamping `last_updated`; don't guess).
- `last_updated`, `days_since_update`, `stale` (`true` once `days_since_update ≥
  stale_days`, default 30) — the re-baseline signal.
- `coaching_intensity` — `light` | `moderate` | `assertive` (default `moderate`).
- `path`, `dir`, `history_count`.

Then **ground yourself**: skim relevant files under `/data/vault` (notes,
journal, projects) so your coaching is rooted in what the operator is actually
doing — not generic advice. Use only the vault and this conversation; don't pull
from calendar/email. Keep it light; a couple of reads, not an audit.

Branch on `exists`:

## 1. No goals yet → elicit them

Walk the horizons **longest first**: 5y → 2y → 1y → 6mo → 3mo → 1mo → 1wk. Ask
about **one horizon at a time** and wait for the answer before moving on — never
dump all seven at once.

Going longest-first is deliberate: it lets each shorter goal be checked against
the longer ones (the **cascade**, below). As you descend, reflect back how the
shorter goal serves the longer — and flag it if it doesn't.

For each horizon, once they give you a goal, help sharpen it before moving on:

- **Make it actionable and achievable.** Gently steer vague aspirations toward
  something they could actually start on. Do **not** demand SMART metrics or
  rigid measurability — a clear, honest next step beats a contrived KPI. Nudge,
  don't interrogate.
- **Surface the obstacle + an if-then plan** (lightly — this is WOOP /
  implementation-intentions, the one technique worth borrowing). Ask what's most
  likely to derail it, and help draft a concrete *"if X happens, then I'll Y."*
  One sentence is plenty. Skip it if the goal is already solid or the operator
  isn't in the mood — never force the scaffold.

When you have all seven, **synthesize** them into the file (§3).

## 2. Goals exist → remind, then coach

1. **Remind first.** Open by reflecting their current goals back concisely —
   every run, the operator should immediately see where they stand. Lead with
   this before any critique.
2. **Coach, at the configured intensity.** Apply `coaching_intensity`:
   - `light` — mostly affirm; offer a gentle suggestion or two; rarely challenge.
   - `moderate` (default) — ask probing questions, name misalignments and
     tradeoffs, propose sharper alternatives — but defer to their final call.
   - `assertive` — actively challenge weak or vague goals, argue the other side,
     don't let a misaligned goal pass without a real exchange. Still never overrule.

   Whatever the level, look for and surface:
   - **Cascade breaks** — a shorter-horizon goal that serves none of the longer
     ones, or a long-horizon goal with nothing beneath it moving it forward.
     This is the highest-signal thing to catch.
   - **Misalignment with reality** — a goal that conflicts with what the vault
     shows they're actually spending time and energy on. Name it kindly and ask.
   - **Drift or staleness** in a specific goal — something they've clearly moved
     past, or that no longer fits who they're becoming.

   Propose concrete refinements; let them accept, reject, or rewrite. If they
   hold firm, record their version — they own the goals.
3. **Re-baseline nudge.** If `stale` is true (default: `last_updated` ≥ 30 days
   ago), mention it and *ask* whether they want a full re-baseline (re-walking
   the horizons). Don't force it; some goals are meant to be long and steady.

The operator can also retune the dial mid-conversation ("push me harder",
"ease off"). When they do, update `coaching_intensity` in the frontmatter (§3).

## 3. Persist

Write `goals.md` under the goals dir. Keep the **frontmatter flat** (the status
script only parses flat keys) and put everything else in the body:

```markdown
---
last_updated: 2026-06-08      # use `today` from the status script
created: 2026-01-15
coaching_intensity: moderate  # light | moderate | assertive
---

# Goals

_Last reviewed 2026-06-08._

## 5 years
<the goal, in their voice — refined, not transcribed>
- **Obstacle / if-then:** <if present; omit the line otherwise>

## 2 years
…

## 1 week
…
```

Guidance for the body:
- One section per horizon, longest → shortest, so the cascade reads top-down.
- Write goals in the operator's own framing — refined, but theirs, not yours.
- Only include the obstacle/if-then line when one was actually drawn out.
- Always set `last_updated` to the script's `today` whenever you change goals.

**History snapshots.** Before overwriting on a *significant* rewrite (a
re-baseline, or a goal materially changed — not a typo fix or a one-line status
tweak), copy the current `goals.md` to `history/goals-<last_updated>.md` first,
so there's a trail of how the goals evolved. Create the `history/` dir if absent.

That's the whole job: read the state, remind or elicit, coach honestly at the
set intensity, and persist. Help the operator as much as possible — steer them,
refine with them, push back when it's warranted — without ever getting in their
way or overruling their call.
