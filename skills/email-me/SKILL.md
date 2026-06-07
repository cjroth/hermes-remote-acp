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

### Body formats

| Flag         | Sends as                | Use for |
|--------------|-------------------------|---------|
| *(none)*     | `text/plain`            | short notes |
| `--markdown` | styled HTML (+ plain fallback) | **reports & digests — the nice path** |
| `--html`     | `text/html` verbatim    | when you've already built the HTML |

`--markdown` is the recommended way to get a **good-looking email**: write the
body in plain Markdown and the script renders it into a clean, responsive HTML
email (system fonts, a centered card, styled headings / links / lists /
blockquotes / code) and sends it as `multipart/alternative` — so HTML clients
get the formatted version and others fall back to the raw Markdown. Supported
Markdown: headings, **bold**, *italic*, `code`, fenced code blocks, links and
bare URLs, ordered/unordered lists, blockquotes, and `---` rules.

### Common forms

```bash
# Plain-text note to the operator (default recipient)
python3 scripts/send.py --subject "Backup done" --body "Nightly backup finished OK."

# Nicely formatted report/digest — write Markdown, pipe it in
cat /tmp/digest.md | python3 scripts/send.py --subject "Daily digest" --markdown --body-file -

# Long body from a file (any format) — more robust than a giant CLI arg
python3 scripts/send.py --subject "Daily digest" --markdown --body-file /tmp/digest.md

# Pre-built HTML (you own the markup)
cat /tmp/report.html | python3 scripts/send.py --subject "Report" --html --body-file -

# Override the recipient or add a Cc
python3 scripts/send.py --to "someone@example.com" --cc "me@example.com" \
    --subject "FYI" --body "..."
```

## Notes

- **Prefer `--body-file` (or stdin) for anything long or with special
  characters** — it avoids shell-quoting pitfalls when the body is large, which
  is the normal case for reports and digests.
- For anything structured, prefer `--markdown` — you write Markdown and get a
  styled HTML email with a plain-text fallback. `--html` sends your markup
  verbatim; with neither flag the body goes as `text/plain`.
- The transport is **localhost-only** — it speaks SMTP to `127.0.0.1:1025`
  (hydroxide); nothing is exposed off the box.
- The default recipient comes from the `USER_PRIMARY_EMAIL` secret; set it once
  per deploy (no code change needed). This is the same variable other skills use
  as "the operator's email" for calendar/email invites.
- If a send fails with a connection error the bridge may be restarting (it's
  supervised and self-heals within a few seconds) — retry once.
