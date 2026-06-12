---
name: avoidance-checkin
description: "Daily check-in that asks what the operator avoided or didn't make time for, logs answers to the vault, and surfaces weekly trend analysis. A lightweight accountability ritual — not judgmental, just honest and reflective."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Productivity, Accountability, Coaching, Habits, Personal]
---

# Avoidance Check-In — daily accountability ritual

Every evening, check in with the operator on what they avoided or didn't make time for. Log their answers, and periodically surface trends so patterns become visible.

This is **not** a guilt trip. The tone is honest, gentle, and reflective — like a friend helping you see what you're tiptoeing around. The point is pattern recognition, not shame.

## 0. Ground yourself

Read the current state before engaging:

1. Read `/data/vault/avoidance-log.md` — this is the running log. On first run it won't exist yet.
2. Read `/data/vault/tasks.md` — active tasks/commitments give context for the question.
3. If a goals file exists (`/data/vault/goals/goals.md`), skim it briefly to ground the conversation in what the operator cares about.

## 1. Ask the question

Ask what they avoided or didn't make time for today — in your own words, conversational. Keep it natural, not robotic. Examples:

- "What's something you avoided today?"
- "Anything you kept putting off, or didn't find time for?"
- "What was the thing you told yourself you'd do, but didn't?"

The operator can answer with:
- **Nothing** — and that's fine! Log it as-is.
- **One or more items** — log each one.
- **A more complex reflection** — that's great too. Capture the gist.

Wait for their reply before proceeding. The cron delivers to their chat, so they'll respond in-thread.

## 2. Log the answer

Append to `/data/vault/avoidance-log.md`. Create it with a header if it doesn't exist.

**Log format:**

```markdown
# Avoidance Log

## 2026-06-12 (Friday)
- Put off starting the event prospector skill — felt ambiguous, didn't know where to start
- Didn't make time for a walk
```

If they said "nothing", log it explicitly:

```markdown
## 2026-06-12 (Friday)
- Nothing avoided today
```

Keep entries in the operator's own words as much as possible. One bullet per avoidance. The date line should include the day of week in parentheses.

## 3. Weekly trend check

After logging, check if a weekly trend analysis is due.

Read the log file and look for the last trend analysis marker — a line like `### Weekly Trend Report — 2026-06-07` (H3 heading). If no trend report exists yet, or the latest one is **7+ days old** (i.e., the date in the heading is ≥7 days before today), then run a trend analysis.

**Trend analysis:**
- Scan all log entries since the last trend report (or all entries if first report).
- Identify common themes: recurring avoidances, types of tasks being put off (creative work, admin, outreach, health, deep work vs shallow work, etc.), days of week patterns, time-of-week correlations.
- Write up a brief, human, insightful trend report (2-5 sentences is plenty — don't overdo it).
- Append it to the log file under a `### Weekly Trend Report — YYYY-MM-DD` heading.
- **Present it to the operator** in the conversation as part of your delivery. Lead with the trend, then the day's log. Make it gentle insight, not scolding.

Example: *"Noticing a pattern — 3 of the last 5 days you've avoided starting 'ambiguous creative projects.' Maybe next time try breaking off just a 5-minute first step before you can talk yourself out of it?"*

## 4. Optional: light coaching

If you see a specific, small, concrete thing that could help with the most commonly logged avoidance, offer one sentence of coaching — no more. Don't push if they're not in the mood. Keep it light.

## Log file location

`/data/vault/avoidance-log.md`

The file lives under the vault so it's in the inotify/CSP sync scope and persists across resets.