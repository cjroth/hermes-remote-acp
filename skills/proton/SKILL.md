---
name: proton
description: "ProtonMail via the local hydroxide bridge: email (IMAP/SMTP), calendar (CalDAV), contacts (CardDAV)."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
prerequisites:
  env_vars: [HYDROXIDE_USER, HYDROXIDE_BRIDGE_PASS]
metadata:
  hermes:
    tags: [ProtonMail, Email, Calendar, Contacts, CalDAV, CardDAV, IMAP, SMTP]
    homepage: https://github.com/emersion/hydroxide
---

# Proton (mail · calendar · contacts)

This box runs **hydroxide**, a self-hosted ProtonMail bridge, exposing Proton
over standard protocols on `127.0.0.1`:

| Protocol | Port | Use for |
|----------|------|---------|
| IMAP     | 1143 | reading mail |
| SMTP     | 1025 | sending mail |
| CalDAV   | 8081 | calendar events |
| CardDAV  | 8080 | contacts |

End-to-end PGP encryption is handled by the bridge — you work with plain mail,
iCalendar, and vCard.

## How to use it

**Always go through the helper script** `scripts/proton.py`. Do not hand-write
IMAP/CalDAV traffic — the script handles auth, the WebDAV XML, time-range
filtering, PGP round-trips, and edge cases (e.g. event creation vs update),
and prints JSON you can parse.

```bash
python3 scripts/proton.py <command> [args]
```

Credentials are read from the environment (`HYDROXIDE_USER`,
`HYDROXIDE_BRIDGE_PASS`), already set on this machine. If they're unset the
script returns `{"error": "..."}`.

### Email

```bash
# recent inbox (newest first)
python3 scripts/proton.py inbox --limit 10
python3 scripts/proton.py inbox --folder Archive --limit 20

# read one message (uid from the inbox/search output)
python3 scripts/proton.py read --folder INBOX 42

# full-text search
python3 scripts/proton.py search "invoice" --folder INBOX

# send (To/Cc accept comma-separated lists)
python3 scripts/proton.py send --to "a@b.com" --subject "Hello" --body "Hi there"
python3 scripts/proton.py send --to "a@b.com,c@d.com" --cc "e@f.com" \
    --subject "Update" --body "..."
```

Folder names are IMAP names: `INBOX`, `Sent`, `Archive`, `Trash`, `Spam`,
`Drafts`, `Starred`, `All Mail`.

### Calendar

```bash
# list calendars (note the name or id)
python3 scripts/proton.py calendars

# events — calendar can be a name substring (e.g. "My calendar") or its id.
# default window is wide (all events); narrow with ISO 8601 --start/--end.
python3 scripts/proton.py events "My calendar"
python3 scripts/proton.py events "My calendar" --start 2026-06-01 --end 2026-07-01

# create (times are ISO 8601; bare times are treated as UTC)
python3 scripts/proton.py create-event "My calendar" \
    --summary "Lunch with Sam" --start 2026-06-10T15:00 --end 2026-06-10T16:00 \
    --location "Cafe" --desc "monthly catch-up"

# invite attendees (repeat --attendee). Proton sends invitations and the
# event records each invitee + RSVP status (shown in `events` output).
python3 scripts/proton.py create-event "My calendar" \
    --summary "Team sync" --start 2026-06-12T17:00 --end 2026-06-12T17:30 \
    --attendee alice@proton.me --attendee bob@example.com

# invite people to an EXISTING event (uid from `events`); emails the new
# invitees and bumps the event SEQUENCE.
python3 scripts/proton.py add-attendee "My calendar" hermes-ab12cd34ef56 \
    --attendee carol@proton.me

# delete by uid (uid comes from `events` output)
python3 scripts/proton.py delete-event "My calendar" hermes-ab12cd34ef56
```

To **update** an event, `delete-event` then `create-event`, or create a fresh
one — the bridge keys events by their iCalendar UID.

### Contacts

```bash
python3 scripts/proton.py contacts
```

Lists contacts (name + emails) across the account's address books.

## Notes & limits

- **The operator's own email** (for calendar/email invites — e.g. inviting
  yourself to an event, or who to address) is the `USER_PRIMARY_EMAIL`
  environment variable. Use it when you need the user's address; if it's unset,
  say so rather than guessing. (`HYDROXIDE_USER` is the Proton login used as the
  transport's From, which may differ from the user's primary inbox.)
- **Creating a calendar** is not supported (the bridge returns 501). Create new
  calendars in the Proton web app; this skill operates on existing ones.
- Everything is **localhost-only** — these ports are never exposed off the
  machine.
- The script is **stdlib-only** Python 3; no extra packages are needed.
- If a command fails with a connection error, the bridge may be restarting —
  it's supervised and self-heals within a few seconds; retry once.
