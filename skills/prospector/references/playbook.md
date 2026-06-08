# Prospector playbook — encodable heuristics

The research-backed rules behind the skill. Read this before strategizing the
top picks and drafting messages. Citations are illustrative, not exhaustive.

## Core stance

You score **the user's own relationship graph** for strategic relationship-
building — not strangers for a sales quota. The asset is the network and its
*paths*; your job is to traverse it well. Be relational, not transactional;
give before you ask; play a 1–3 move game, not a single jump.

## Networking-strategy frameworks (the "4D chess")

- **Strength of weak ties (Granovetter).** Weak/bridging ties carry *novel*
  information and opportunities because their circles don't overlap yours;
  strong ties give trust and vouching. → For *new* reach/info/opportunity,
  prioritize weak and bridging ties. For a vouch or a high-stakes intro, use a
  strong tie.
- **Structural holes / brokers (Burt).** Value is *position*, not warmth: a
  person who bridges two clusters you can't otherwise reach (a "super-connector")
  is a priority both as a target and as an intro route. Mark them
  `super_connector: true`.
- **Two-hop traversal.** Model intros as a graph; find the shortest warm path
  to a cold target. **Cap path search at 2 hops (occasionally 3).** A path is
  only as warm as its *coldest* link — rank candidate paths by their weakest
  edge. If a target is unreachable, don't cold-pitch them: pick a reachable
  intermediary who connects to them, nurture/give to the intermediary first,
  then request the intro. Treat each intermediary as a sub-goal.
- **Give-first (Feld).** Attach a give to every reach — an intro, an insight, a
  resource, useful feedback. Track `gives`/`asks` per person; when asks outrun
  gives, lead with a give and hold the ask.
- **Dormant ties (Grant).** People you were once close to but lost touch with
  are the **highest-ROI, lowest-cost** reconnections: pre-existing trust, but
  they've drifted into different circles and now carry fresh information. Surface
  them aggressively (the `reactivate` mode). Reactivate giver-style: open with
  an offer or a genuine "you came to mind because…", not a cold ask.

## Mode router (decide the play first)

Classify each target from `(reachability, relationship strength, value)`:

- **`nurture`** — an active tie. No hard ask; give-first; driven by cadence
  (`now − last_touch > cadence_days`). Cadence varies by tier: a mentor,
  a hiring manager, and a conference acquaintance should not share a rhythm.
- **`reactivate`** — a dormant strong/advocate tie gone quiet. Highest ROI.
- **`warm-intro`** — a 1–2 hop path exists to a valuable/cold target. **Default
  for high-value targets** (warm converts ~10–20× cold). Use the double-opt-in
  protocol below.
- **`cold`** — no path. Lowest conversion; reserve for high-value targets where
  you bring an *undeniable* hook (a real trigger + specific value). Otherwise,
  find a path instead.

## Trigger → message-angle table

A surfaced signal should dictate the opening line. Common triggers:

| Trigger | Angle to open with |
|---------|--------------------|
| Funding round / new budget | Congrats + a specific, relevant observation tied to what the round enables |
| New role / job change (≤90d) | "New-chapter" angle — new hires want quick wins and have fresh mandate |
| Product launch / ship | React substantively to the thing they shipped (used it, have a sharp take) |
| Published post / talk / paper | Engage with the *idea*, add a non-obvious point, then the ask |
| Hiring for a problem you know | Reference the problem their job posts reveal |
| Mutual connection / shared context | Lead with the bridge |

No trigger and no path → usually not yet worth a cold reach; nurture toward a
path or wait for a trigger.

## Channel choice (lookup)

- **Warm intro / in-person / event** — highest conversion; reserve for high-value
  targets where a path exists.
- **LinkedIn DM** — 3–5× higher reply than cold email when personalized; best
  default for professional/career and most B2B.
- **Email** — when you have a real address and a strong trigger; scales follow-ups.
- **X/Twitter** — **engage before you DM**: add a substantive reply to their
  posts first, *then* a brutally short manual DM (one idea). Strong for founders,
  VCs, and creators who live there.
- Pick the channel where the person is *actually active and receptive*, not the
  one that's easiest for you.

## Message rules (apply verbatim when drafting)

- **Length:** 50–125 words; under ~80 for senior/busy people. The user asked for
  2 sentences to 2 short paragraphs — stay in that band.
- **Personalization test:** if you can delete the personalized opening and the
  message still makes sense, it isn't personalized. The hook must be specific to
  *them*.
- **Single, low-friction ask:** one ask, one sentence, easy to say yes to and
  easy to decline. Prefer interest-based ("worth a quick exchange?") over
  calendar-based ("30-min call?"). In a first founder/peer email, often ask a
  question they can answer in one line — don't request a call in message #1.
- **Reader-centric:** "you/your" should outweigh "I/we." Peer voice, not seller
  voice.
- **Seniority rule:** the more senior/busy, the shorter. 3 sentences + one
  question reads as respect.
- **Subject lines:** 2–4 words, lowercase, internal-looking; no pitch, no
  urgency, no emoji.
- **Cut:** "hope this finds you well," jargon (synergy/leverage), feature dumps,
  multi-ask paragraphs.
- **Directness calibration:** the warmer the tie and the smaller the status gap,
  the more direct the ask can be. For cold or high-status recipients, use the
  *indirect* ask — advice/learning, not a favor. ("Ask for advice and you get
  help twice; ask for a job and you get neither.")

## Investor outreach (special rules)

- **Warm intro >> cold** (~10–20× to a first meeting; warm intros raise funding
  odds ~13×). The connector spends *their own* social capital, so make the vouch
  effortless.
- **Double opt-in + forwardable blurb.** Ask the connector privately first (a
  short personal note at the top); attach a **<150-word forwardable blurb** at
  the bottom they can forward in ≤15 seconds. The blurb states: what you do,
  **traction in numbers**, team, what you want, and the **specific reason this
  investor** (their thesis / a portfolio company / something they wrote). Wait
  for the connector's OK before the intro fires.
- **Why this won't waste their time** (the framing the user explicitly wants):
  lead with the single strongest, *undeniable* signal (real traction in numbers,
  or perfect thesis/stage/geo fit referenced explicitly); be 4–6 sentences; one
  clear, low-friction ask.
- **"Not raising yet" play:** state plainly there's no ask — share one concrete
  metric/update and aim for a one-line reply. This converts a cold investor into
  a nurtured tie so the eventual raise is already warm. (This is give-first +
  nurture, not a pitch.)

## Job / career networking

- **Informational interview = a learning conversation, not a disguised job ask.**
  Explicitly asking for a job negates it; leads emerge indirectly.
- Calibrate ask-directness by relationship strength × status gap (above).
- Highest-ROI moves: **reactivate dormant ties**, and match your existing
  contacts against target companies (where do you already have a connection?).

## ICP / quality gate (before adding anyone)

Before creating a person file, gate on: *does reaching this person plausibly
advance a current goal in goals.md?* If not, don't add them. Reassess the
direction (and the category weights in rank-people.py) when goals shift.
