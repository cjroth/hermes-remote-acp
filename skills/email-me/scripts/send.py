#!/usr/bin/env python3
"""Send an email to the operator over the Proton (hydroxide) SMTP transport.

This is the generic "send *something* to me" transport. Any skill that wants to
reach the operator by email shells out to this script; it owns the recipient
default and the connection details so callers only supply subject + body.

It talks plain SMTP to the local hydroxide bridge (the same transport the
`proton` skill uses); the bridge handles ProtonMail auth and PGP. Stdlib only.

Body formats:
    (default)    text/plain — sent verbatim
    --markdown   render Markdown into a clean, styled HTML email (recommended
                 for digests/reports). Sent as multipart/alternative so clients
                 without HTML still get the raw Markdown as plain text.
    --html       caller-supplied HTML, sent verbatim as text/html

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
    cat digest.md | send.py --subject "Daily digest" --markdown --body-file -
"""
import argparse
import email.utils
import html as html_lib
import json
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
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


# ---------------------------------------------------------------------------
# Minimal Markdown -> HTML (stdlib only). Covers what reports/digests need:
# headings, paragraphs, bold/italic/code, links (and bare URLs), ordered and
# unordered lists, blockquotes, fenced code blocks, and horizontal rules.
# ---------------------------------------------------------------------------
def _inline(text):
    """Render inline Markdown in an already-block-split line."""
    stash = []

    def put(html):
        stash.append(html)
        return f"\x00{len(stash) - 1}\x00"

    text = html_lib.escape(text, quote=False)
    # inline code first so * _ inside it aren't treated as emphasis
    text = re.sub(r"`([^`]+)`", lambda m: put("<code>" + m.group(1) + "</code>"), text)
    # [label](url)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  lambda m: put(f'<a href="{m.group(2)}">{m.group(1)}</a>'), text)
    # bare URLs (stash so emphasis regexes can't corrupt them)
    text = re.sub(r"(https?://[^\s<>()]+)",
                  lambda m: put(f'<a href="{m.group(1)}">{m.group(1)}</a>'), text)
    # emphasis
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
    # restore stashed spans
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def _render_markdown(md):
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, para, i, n = [], [], 0, len(lines)

    def flush():
        if para:
            joined = " ".join(para).strip()
            if joined:
                out.append("<p>" + _inline(joined) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):                       # fenced code
            flush()
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html_lib.escape("\n".join(code)) + "</code></pre>")
            continue
        if s == "":                                    # blank
            flush()
            i += 1
            continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):   # horizontal rule
            flush()
            out.append("<hr>")
            i += 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)$", s)           # ATX heading
        if m:
            flush()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>" + _inline(m.group(2).strip()) + f"</h{lvl}>")
            i += 1
            continue
        if s.startswith(">"):                          # blockquote (recursive)
            flush()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + _render_markdown("\n".join(quote)) + "</blockquote>")
            continue
        if re.match(r"[-*+]\s+", s):                    # unordered list
            flush()
            items = []
            while i < n and re.match(r"\s*[-*+]\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip()) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"\d+\.\s+", s):                    # ordered list
            flush()
            items = []
            while i < n and re.match(r"\s*\d+\.\s+", lines[i]):
                items.append("<li>" + _inline(re.sub(r"^\s*\d+\.\s+", "", lines[i]).strip()) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        para.append(s)                                 # paragraph text
        i += 1
    flush()
    return "\n".join(out)


# A constrained, email-client-friendly shell. Styles live in <head> (Proton,
# Apple Mail, most modern clients honor them); the layout still reads fine if a
# client strips them, since it's a single centered column of semantic HTML.
_HTML_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin:0; padding:0; background:#f5f6f8;
          -webkit-text-size-adjust:100%; }}
  .wrap {{ max-width:680px; margin:0 auto; padding:24px 16px; }}
  .card {{ background:#ffffff; border:1px solid #e5e7eb; border-radius:10px;
           padding:28px 32px; }}
  .card, .card p, .card li, .card blockquote {{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    color:#1f2933; font-size:15px; line-height:1.6; }}
  h1 {{ font-size:22px; line-height:1.3; margin:0 0 16px; color:#111827; }}
  h2 {{ font-size:18px; line-height:1.3; margin:28px 0 8px; color:#111827;
        border-top:1px solid #eef0f3; padding-top:18px; }}
  h3 {{ font-size:16px; margin:20px 0 6px; color:#111827; }}
  p {{ margin:0 0 14px; }}
  a {{ color:#2563eb; text-decoration:none; }}
  ul, ol {{ margin:0 0 14px; padding-left:22px; }}
  li {{ margin:4px 0; }}
  blockquote {{ margin:0 0 14px; padding:4px 14px; border-left:3px solid #d1d5db;
                color:#52606d; background:#f9fafb; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
          font-size:13px; background:#f3f4f6; padding:1px 5px; border-radius:4px; }}
  pre {{ background:#f3f4f6; padding:14px 16px; border-radius:8px; overflow-x:auto; }}
  pre code {{ background:none; padding:0; }}
  hr {{ border:0; border-top:1px solid #e5e7eb; margin:22px 0; }}
</style>
</head>
<body>
  <div class="wrap"><div class="card">
{inner}
  </div></div>
</body>
</html>"""


def markdown_to_email_html(md, title):
    return _HTML_SHELL.format(title=html_lib.escape(title), inner=_render_markdown(md))


def build_message(args, body):
    """Return a MIME message for the chosen body format."""
    if args.markdown:
        root = MIMEMultipart("alternative")
        root.attach(MIMEText(body, "plain", "utf-8"))      # fallback = raw markdown
        root.attach(MIMEText(markdown_to_email_html(body, args.subject), "html", "utf-8"))
        return root
    return MIMEText(body, "html" if args.html else "plain", "utf-8")


def main():
    p = argparse.ArgumentParser(description="Email the operator via the Proton bridge")
    p.add_argument("--to", default=DEFAULT_TO,
                   help="recipient(s), comma-separated (default: $USER_PRIMARY_EMAIL)")
    p.add_argument("--cc", default="")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", help="body text; or use --body-file / stdin")
    p.add_argument("--body-file", dest="body_file",
                   help="read body from this file ('-' for stdin)")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--markdown", action="store_true",
                     help="render the body (Markdown) into a clean styled HTML email")
    fmt.add_argument("--html", action="store_true",
                     help="send the body verbatim as text/html")
    args = p.parse_args()

    if not USER or not PASS:
        die("HYDROXIDE_USER and HYDROXIDE_BRIDGE_PASS must be set in the environment")

    if not args.to:
        die("USER_PRIMARY_EMAIL is not set — set it (the operator's inbox) or "
            "pass --to explicitly")

    body = read_body(args)
    msg = build_message(args, body)
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

    fmt_name = "markdown" if args.markdown else ("html" if args.html else "plain")
    print(json.dumps({"sent": True, "to": rcpts, "subject": args.subject, "format": fmt_name}))


if __name__ == "__main__":
    main()
