---
name: email-me
description: "Send something to the operator by email (notifications, reports, digests) over the local Proton/hydroxide SMTP transport. Use whenever a skill or task needs to deliver a message to the user's inbox."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
prerequisites:
  env_vars: [HYDROXIDE_USER, HYDROXIDE_BRIDGE_PASS, USER_PRIMARY_EMAIL]
metadata:
  hermes:
    tags: [Email, Notify, Proton, SMTP, Transport]
---

# Email me

A thin, reusable **transport**: send *something* — a notification, a report, a
digest — to the operator's primary inbox. It wraps the local hydroxide SMTP
bridge (the same Proton transport the `proton` skill uses) so other skills don't
have to know the recipient address or the bridge details. They just hand it a
subject and a body.

The recipient is the operator's primary email, read from the
`USER_PRIMARY_EMAIL` environment variable — whoever runs this skill sets it.
Callers normally don't pass `--to`. There is **no hardcoded address**: if
`USER_PRIMARY_EMAIL` isn't set and no `--to` is given, the script returns
`{"error": "USER_PRIMARY_EMAIL is not set ..."}` instead of guessing.

## How to use it

Always go through the helper script:

```bash
python3 scripts/send.py --subject "<subject>" --body "<text>"
```

Recipient resolution (first that is set wins): `--to` → `USER_PRIMARY_EMAIL`
env. Credentials (`HYDROXIDE_USER`, `HYDROXIDE_BRIDGE_PASS`) are read from the
environment, already set on this machine. The script prints JSON:
`{"sent": true, ...}` or `{"error": "..."}`. If `USER_PRIMARY_EMAIL` is unset
and no `--to` is passed, it reports that the email isn't set.

### Common forms

```bash
# Plain-text note to the operator (default recipient)
python3 scripts/send.py --subject "Backup done" --body "Nightly backup finished OK."

# Long / structured body — pass a file instead of a giant CLI arg (more robust)
python3 scripts/send.py --subject "Daily digest" --body-file /tmp/digest.txt

# HTML email — render a nicer report; pipe the body in on stdin
cat /tmp/digest.html | python3 scripts/send.py --subject "Daily digest" --html --body-file -

# Override the recipient or add a Cc
python3 scripts/send.py --to "someone@example.com" --cc "me@example.com" \
    --subject "FYI" --body "..."
```

## Notes

- **Prefer `--body-file` (or stdin) for anything long or with special
  characters** — it avoids shell-quoting pitfalls when the body is large, which
  is the normal case for reports and digests.
- `--html` sends a `text/html` message; without it the body goes as
  `text/plain` (most clients auto-linkify bare URLs, so plain text is fine).
- The transport is **localhost-only** — it speaks SMTP to `127.0.0.1:1025`
  (hydroxide); nothing is exposed off the box.
- The default recipient comes from the `USER_PRIMARY_EMAIL` secret; set it once
  per deploy (no code change needed). This is the same variable other skills use
  as "the operator's email" for calendar/email invites.
- If a send fails with a connection error the bridge may be restarting (it's
  supervised and self-heals within a few seconds) — retry once.
