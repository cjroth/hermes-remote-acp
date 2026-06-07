#!/usr/bin/env python3
"""Send an email to the operator over the Proton (hydroxide) SMTP transport.

This is the generic "send *something* to me" transport. Any skill that wants to
reach the operator by email shells out to this script; it owns the recipient
default and the connection details so callers only supply subject + body.

It talks plain SMTP to the local hydroxide bridge (the same transport the
`proton` skill uses); the bridge handles ProtonMail auth and PGP. Stdlib only.

Recipient resolution (first that is set wins):
    --to argument  >  USER_PRIMARY_EMAIL env

There is no hardcoded recipient: whoever runs the skill is expected to set
USER_PRIMARY_EMAIL. If neither --to nor USER_PRIMARY_EMAIL is set, the script
returns a clear "not set" error rather than guessing an address.

Environment (already set on the box for the bridge):
    HYDROXIDE_USER         Proton address used as the From / SMTP login (required)
    HYDROXIDE_BRIDGE_PASS  bridge password from `hydroxide auth`        (required)
    HYDROXIDE_HOST         default 127.0.0.1
    HYDROXIDE_SMTP_PORT    default 1025
    USER_PRIMARY_EMAIL     operator's inbox; the default recipient (required
                           unless --to is passed)

Examples:
    send.py --subject "hi" --body "hello"                 # -> USER_PRIMARY_EMAIL
    send.py --subject "Report" --body-file /tmp/r.txt
    cat report.html | send.py --subject "Digest" --html --body-file -
"""
import argparse
import email.utils
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText

# Operator's primary inbox. Set per-deploy via the USER_PRIMARY_EMAIL secret;
# there is no hardcoded default — whoever runs the skill provides their own.
DEFAULT_TO = os.environ.get("USER_PRIMARY_EMAIL", "")

HOST = os.environ.get("HYDROXIDE_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("HYDROXIDE_SMTP_PORT", "1025"))
USER = os.environ.get("HYDROXIDE_USER", "")
PASS = os.environ.get("HYDROXIDE_BRIDGE_PASS", "")


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def read_body(args):
    if args.body is not None:
        return args.body
    if args.body_file:
        if args.body_file == "-":
            return sys.stdin.read()
        with open(args.body_file, "r", encoding="utf-8") as fh:
            return fh.read()
    # No explicit body: fall back to stdin if it's piped in.
    if not sys.stdin.isatty():
        return sys.stdin.read()
    die("provide a body via --body, --body-file, or stdin")


def main():
    p = argparse.ArgumentParser(description="Email the operator via the Proton bridge")
    p.add_argument("--to", default=DEFAULT_TO,
                   help="recipient(s), comma-separated (default: $USER_PRIMARY_EMAIL)")
    p.add_argument("--cc", default="")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", help="body text; or use --body-file / stdin")
    p.add_argument("--body-file", dest="body_file",
                   help="read body from this file ('-' for stdin)")
    p.add_argument("--html", action="store_true",
                   help="send the body as text/html instead of text/plain")
    args = p.parse_args()

    if not USER or not PASS:
        die("HYDROXIDE_USER and HYDROXIDE_BRIDGE_PASS must be set in the environment")

    if not args.to:
        die("USER_PRIMARY_EMAIL is not set — set it (the operator's inbox) or "
            "pass --to explicitly")

    body = read_body(args)
    msg = MIMEText(body, "html" if args.html else "plain", "utf-8")
    msg["Subject"] = args.subject
    msg["From"] = USER
    msg["To"] = args.to
    if args.cc:
        msg["Cc"] = args.cc
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()

    rcpts = [a.strip() for a in
             (args.to + ("," + args.cc if args.cc else "")).split(",") if a.strip()]
    if not rcpts:
        die("no recipient resolved")

    s = smtplib.SMTP(HOST, SMTP_PORT, timeout=30)
    try:
        s.ehlo()
        s.login(USER, PASS)
        s.sendmail(USER, rcpts, msg.as_string())
    except Exception as e:  # noqa: BLE001 - report any transport failure as JSON
        die(f"send failed: {e}")
    finally:
        s.quit()

    print(json.dumps({"sent": True, "to": rcpts, "subject": args.subject,
                      "html": args.html}))


if __name__ == "__main__":
    main()
