#!/usr/bin/env python3
"""Proton bridge helper for the Hermes agent.

Talks to the local hydroxide bridge (IMAP/SMTP/CalDAV/CardDAV on 127.0.0.1)
so the agent can use ProtonMail mail, calendar, and contacts with reliable,
deterministic commands instead of hand-rolling protocol traffic.

Stdlib only (imaplib / smtplib / urllib) — no pip deps.

Connection comes from the environment (set by the Fly deploy):
  HYDROXIDE_USER         Proton address, e.g. you@proton.me        (required)
  HYDROXIDE_BRIDGE_PASS  bridge password from `hydroxide auth`     (required)
  HYDROXIDE_HOST         default 127.0.0.1
  HYDROXIDE_IMAP_PORT    default 1143
  HYDROXIDE_SMTP_PORT    default 1025
  HYDROXIDE_CALDAV_PORT  default 8081
  HYDROXIDE_CARDDAV_PORT default 8080

All output is JSON on stdout so the agent can parse it. Errors -> JSON
{"error": "..."} on stdout and a non-zero exit.

Examples:
  proton.py inbox --limit 10
  proton.py send --to a@b.com --subject "hi" --body "hello"
  proton.py calendars
  proton.py events "My calendar"
  proton.py create-event "My calendar" --summary "Lunch" \\
      --start 2026-06-10T15:00 --end 2026-06-10T16:00 --location "Cafe"
  proton.py delete-event "My calendar" <uid>
  proton.py contacts
"""
import argparse
import datetime as dt
import email
import email.utils
import imaplib
import json
import os
import re
import smtplib
import sys
import urllib.request
import uuid
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

HOST = os.environ.get("HYDROXIDE_HOST", "127.0.0.1")
USER = os.environ.get("HYDROXIDE_USER", "")
PASS = os.environ.get("HYDROXIDE_BRIDGE_PASS", "")
IMAP_PORT = int(os.environ.get("HYDROXIDE_IMAP_PORT", "1143"))
SMTP_PORT = int(os.environ.get("HYDROXIDE_SMTP_PORT", "1025"))
CALDAV_PORT = int(os.environ.get("HYDROXIDE_CALDAV_PORT", "8081"))
CARDDAV_PORT = int(os.environ.get("HYDROXIDE_CARDDAV_PORT", "8080"))


def die(msg):
    print(json.dumps({"error": str(msg)}))
    sys.exit(1)


def need_creds():
    if not USER or not PASS:
        die("HYDROXIDE_USER and HYDROXIDE_BRIDGE_PASS must be set in the environment")


def out(obj):
    print(json.dumps(obj, indent=2, default=str))


# ----------------------------------------------------------------------------
# WebDAV (CalDAV / CardDAV) plumbing
# ----------------------------------------------------------------------------
def dav(method, port, path, body=None, depth=None, ctype="application/xml"):
    import base64
    url = f"http://{HOST}:{port}{path}"
    headers = {"Authorization": "Basic " + base64.b64encode(f"{USER}:{PASS}".encode()).decode()}
    if depth is not None:
        headers["Depth"] = str(depth)
    data = None
    if body is not None:
        headers["Content-Type"] = ctype
        data = body.encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _responses(xml):
    return re.findall(r"<(?:[a-z0-9]+:)?response\b.*?</(?:[a-z0-9]+:)?response>", xml, re.S | re.I)


def _tag(chunk, tag):
    m = re.search(rf"<(?:[a-z0-9]+:)?{tag}\b[^>]*>(.*?)</(?:[a-z0-9]+:)?{tag}>", chunk, re.S | re.I)
    return m.group(1).strip() if m else None


def _href(chunk):
    return _tag(chunk, "href")


# ----------------------------------------------------------------------------
# Calendar (CalDAV)
# ----------------------------------------------------------------------------
def list_calendars():
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>")
    st, xml = dav("PROPFIND", CALDAV_PORT, "/caldav/calendars/", body, depth=1)
    if st not in (207, 200):
        die(f"list calendars failed: HTTP {st}: {xml[:300]}")
    cals = []
    for chunk in _responses(xml):
        href = _href(chunk)
        if not href or "calendar" not in chunk.lower():
            continue
        if href.rstrip("/").endswith("/calendars"):
            continue
        cals.append({"id": href.rstrip("/").split("/")[-1],
                     "name": _tag(chunk, "displayname") or "",
                     "href": href.rstrip("/")})
    return cals


def resolve_calendar(needle):
    cals = list_calendars()
    for c in cals:
        if c["id"] == needle:
            return c
    matches = [c for c in cals if needle.lower() in (c["name"] or "").lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        die(f"no calendar matches {needle!r}; available: {[c['name'] for c in cals]}")
    die(f"{needle!r} is ambiguous: {[c['name'] for c in matches]}")


def _ics_dt(s):
    # Accept ISO 8601 (with or without seconds/Z) -> CalDAV UTC basic form.
    s = s.strip()
    if re.fullmatch(r"\d{8}T\d{6}Z?", s):
        return s if s.endswith("Z") else s + "Z"
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        die(f"bad datetime {s!r}; use ISO 8601 like 2026-06-10T15:00 or 20260610T150000Z")
    if d.tzinfo:
        d = d.astimezone(dt.timezone.utc)
    return d.strftime("%Y%m%dT%H%M%SZ")


def list_events(cal_needle, start, end):
    cal = resolve_calendar(cal_needle)
    s = _ics_dt(start) if start else "20000101T000000Z"
    e = _ics_dt(end) if end else "20400101T000000Z"
    body = (f'<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            f"<d:prop><d:getetag/><c:calendar-data/></d:prop>"
            f'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            f'<c:time-range start="{s}" end="{e}"/></c:comp-filter></c:comp-filter></c:filter>'
            f"</c:calendar-query>")
    st, xml = dav("REPORT", CALDAV_PORT, cal["href"], body, depth=1)
    if st not in (207, 200):
        die(f"list events failed: HTTP {st}: {xml[:300]}")
    events = []
    for chunk in _responses(xml):
        data = _tag(chunk, "calendar-data")
        if not data:
            continue
        data = (data.replace("&#13;", "").replace("&#xD;", "").replace("&#10;", "\n")
                    .replace("&#xA;", "\n").replace("&amp;", "&"))

        def field(name):
            m = re.search(rf"^{name}[:;][^\r\n]*", data, re.M)
            return m.group(0).split(":", 1)[-1].strip() if m else None
        # ATTENDEE repeats; capture each invitee's email + PARTSTAT (RSVP).
        attendees = []
        for line in re.findall(r"^ATTENDEE[^\r\n]*", data, re.M):
            email = line.split("mailto:", 1)[-1].strip() if "mailto:" in line else None
            ps = re.search(r"PARTSTAT=([^;:]+)", line)
            attendees.append({"email": email, "status": ps.group(1) if ps else None})
        events.append({"uid": field("UID"), "summary": field("SUMMARY"),
                       "start": field("DTSTART"), "end": field("DTEND"),
                       "location": field("LOCATION"), "attendees": attendees,
                       "href": _href(chunk)})
    return {"calendar": cal["name"], "count": len(events), "events": events}


def _send_invite_email(attendee, summary, vevent_lines):
    # iMIP invitation. Proton's send API only accepts a text/plain or text/html
    # body, so the calendar goes as a text/calendar;method=REQUEST ATTACHMENT
    # (clients, incl. Proton, detect ICS attachments as invitations). hydroxide
    # routes the plain part as the body and uploads the .ics as an attachment.
    invite = "\r\n".join(
        ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//hermes//proton-skill//EN",
         "METHOD:REQUEST"] + vevent_lines + ["END:VCALENDAR"]) + "\r\n"

    root = MIMEMultipart("mixed")
    root["From"] = USER
    root["To"] = attendee
    root["Subject"] = f"Invitation: {summary}"
    root["Date"] = email.utils.formatdate(localtime=True)
    root["Message-ID"] = email.utils.make_msgid(domain="proton.me")
    root.attach(MIMEText(f"You're invited to: {summary}", "plain", "utf-8"))

    cal = MIMEBase("text", "calendar")
    cal.set_param("method", "REQUEST")
    cal.set_param("charset", "UTF-8")
    cal.set_payload(invite.encode("utf-8"))
    encoders.encode_base64(cal)
    cal.add_header("Content-Disposition", "attachment", filename="invite.ics")
    root.attach(cal)

    s = smtplib.SMTP(HOST, SMTP_PORT, timeout=30)
    try:
        s.ehlo()
        s.login(USER, PASS)
        s.sendmail(USER, [attendee], root.as_bytes())
    finally:
        s.quit()


def create_event(cal_needle, summary, start, end, desc, location, attendees=None):
    cal = resolve_calendar(cal_needle)
    uid = "hermes-" + uuid.uuid4().hex[:12]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    vevent = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}",
              f"DTSTART:{_ics_dt(start)}", f"DTEND:{_ics_dt(end)}", f"SUMMARY:{summary}"]
    if desc:
        vevent.append(f"DESCRIPTION:{desc}")
    if location:
        vevent.append(f"LOCATION:{location}")
    clean = [a.strip() for a in (attendees or []) if a.strip()]
    if clean:
        # An event with attendees needs an ORGANIZER (the account itself).
        vevent.append(f"ORGANIZER;CN={USER}:mailto:{USER}")
        for a in clean:
            vevent.append(
                f"ATTENDEE;CN={a};ROLE=REQ-PARTICIPANT;RSVP=TRUE;"
                f"PARTSTAT=NEEDS-ACTION:mailto:{a}")
    vevent.append("SEQUENCE:0")
    vevent.append("END:VEVENT")

    ics = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0",
                       "PRODID:-//hermes//proton-skill//EN"] + vevent + ["END:VCALENDAR"]) + "\r\n"
    st, xml = dav("PUT", CALDAV_PORT, f"{cal['href']}/{uid}.ics", ics,
                  ctype="text/calendar; charset=utf-8")
    if st not in (201, 204):
        die(f"create event failed: HTTP {st}: {xml[:300]}")

    # Deliver invitations: the calendar API stores attendees, but the actual
    # invite (which makes the event appear in the invitee's calendar) is an
    # iMIP email the organizer sends.
    invited, invite_errors = [], {}
    for a in clean:
        try:
            _send_invite_email(a, summary, vevent)
            invited.append(a)
        except Exception as e:
            invite_errors[a] = repr(e)

    result = {"created": True, "uid": uid, "calendar": cal["name"],
              "summary": summary, "attendees": clean, "invited": invited}
    if invite_errors:
        result["invite_errors"] = invite_errors
    return result


def delete_event(cal_needle, uid):
    res = list_events(cal_needle, None, None)
    match = [e for e in res["events"] if e["uid"] == uid]
    if not match:
        die(f"no event with uid {uid!r} in {res['calendar']!r}")
    st, xml = dav("DELETE", CALDAV_PORT, match[0]["href"])
    if st not in (200, 204):
        die(f"delete failed: HTTP {st}: {xml[:300]}")
    return {"deleted": True, "uid": uid}


# ----------------------------------------------------------------------------
# Contacts (CardDAV)
# ----------------------------------------------------------------------------
# hydroxide exposes a single fixed address book; no discovery needed.
CARDDAV_BOOK = os.environ.get("HYDROXIDE_CARDDAV_BOOK", "/contacts/default")


def list_contacts():
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
            "<d:prop><d:getetag/><c:address-data/></d:prop></d:propfind>")
    st, xml = dav("PROPFIND", CARDDAV_PORT, CARDDAV_BOOK + "/", body, depth=1)
    if st not in (207, 200):
        die(f"list contacts failed: HTTP {st}: {xml[:300]}")
    contacts = []
    for chunk in _responses(xml):
        href = _href(chunk)
        vcard = _tag(chunk, "address-data")
        if not href or not vcard:
            continue
        vcard = (vcard.replace("&#13;", "").replace("&#xD;", "").replace("&#10;", "\n")
                      .replace("&#xA;", "\n").replace("&amp;", "&"))
        fn = re.search(r"^FN[^:]*:(.+)$", vcard, re.M)
        emails = re.findall(r"^EMAIL[^:]*:(.+)$", vcard, re.M)
        tels = re.findall(r"^TEL[^:]*:(.+)$", vcard, re.M)
        contacts.append({"name": fn.group(1).strip() if fn else None,
                         "emails": [e.strip() for e in emails],
                         "phones": [t.strip() for t in tels], "href": href.rstrip("/")})
    return {"count": len(contacts), "contacts": contacts}


# ----------------------------------------------------------------------------
# Email (IMAP / SMTP)
# ----------------------------------------------------------------------------
def imap_conn():
    # Explicit timeout so a wedged bridge surfaces an error instead of hanging.
    m = imaplib.IMAP4(HOST, IMAP_PORT, timeout=30)
    m.login(USER, PASS)
    return m


def list_inbox(folder, limit):
    m = imap_conn()
    try:
        m.select(folder, readonly=True)
        typ, data = m.search(None, "ALL")
        ids = data[0].split()
        ids = ids[-limit:][::-1] if limit else ids[::-1]
        msgs = []
        for i in ids:
            typ, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] FLAGS)")
            hdr = b"".join(p[1] for p in d if isinstance(p, tuple))
            msg = email.message_from_bytes(hdr)
            flags = imaplib.ParseFlags(d[0][0]) if d and d[0] else ()
            msgs.append({"uid": i.decode(), "from": msg.get("From"),
                         "subject": msg.get("Subject"), "date": msg.get("Date"),
                         "seen": b"\\Seen" in flags})
        return {"folder": folder, "count": len(msgs), "messages": msgs}
    finally:
        m.logout()


def read_message(folder, uid):
    m = imap_conn()
    try:
        m.select(folder, readonly=True)
        typ, d = m.fetch(uid.encode(), "(RFC822)")
        if not d or not d[0]:
            die(f"message {uid} not found in {folder}")
        msg = email.message_from_bytes(d[0][1])
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
        return {"uid": uid, "from": msg.get("From"), "to": msg.get("To"),
                "subject": msg.get("Subject"), "date": msg.get("Date"), "body": body}
    finally:
        m.logout()


def search_mail(folder, query, limit):
    m = imap_conn()
    try:
        m.select(folder, readonly=True)
        typ, data = m.search(None, "TEXT", f'"{query}"')
        ids = data[0].split()[-limit:][::-1] if limit else data[0].split()[::-1]
        msgs = []
        for i in ids:
            typ, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            hdr = b"".join(p[1] for p in d if isinstance(p, tuple))
            msg = email.message_from_bytes(hdr)
            msgs.append({"uid": i.decode(), "from": msg.get("From"),
                         "subject": msg.get("Subject"), "date": msg.get("Date")})
        return {"folder": folder, "query": query, "count": len(msgs), "messages": msgs}
    finally:
        m.logout()


def send_mail(to, subject, body, cc):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = USER
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    rcpts = [a.strip() for a in (to + ("," + cc if cc else "")).split(",") if a.strip()]
    s = smtplib.SMTP(HOST, SMTP_PORT, timeout=30)
    try:
        s.ehlo()
        s.login(USER, PASS)
        s.sendmail(USER, rcpts, msg.as_string())
    finally:
        s.quit()
    return {"sent": True, "to": rcpts, "subject": subject}


# ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Proton bridge helper (hydroxide)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("inbox", help="list recent messages in a folder")
    sp.add_argument("--folder", default="INBOX")
    sp.add_argument("--limit", type=int, default=15)

    sp = sub.add_parser("read", help="read one message")
    sp.add_argument("--folder", default="INBOX")
    sp.add_argument("uid")

    sp = sub.add_parser("search", help="full-text search a folder")
    sp.add_argument("query")
    sp.add_argument("--folder", default="INBOX")
    sp.add_argument("--limit", type=int, default=15)

    sp = sub.add_parser("send", help="send an email")
    sp.add_argument("--to", required=True)
    sp.add_argument("--subject", required=True)
    sp.add_argument("--body", required=True)
    sp.add_argument("--cc")

    sub.add_parser("calendars", help="list calendars")

    sp = sub.add_parser("events", help="list events in a calendar")
    sp.add_argument("calendar")
    sp.add_argument("--start")
    sp.add_argument("--end")

    sp = sub.add_parser("create-event", help="create a calendar event")
    sp.add_argument("calendar")
    sp.add_argument("--summary", required=True)
    sp.add_argument("--start", required=True)
    sp.add_argument("--end", required=True)
    sp.add_argument("--desc")
    sp.add_argument("--location")
    sp.add_argument("--attendee", action="append", metavar="EMAIL",
                    help="invite an attendee (repeatable)")

    sp = sub.add_parser("delete-event", help="delete a calendar event by uid")
    sp.add_argument("calendar")
    sp.add_argument("uid")

    sub.add_parser("contacts", help="list contacts")

    a = p.parse_args()
    need_creds()

    if a.cmd == "inbox":
        out(list_inbox(a.folder, a.limit))
    elif a.cmd == "read":
        out(read_message(a.folder, a.uid))
    elif a.cmd == "search":
        out(search_mail(a.folder, a.query, a.limit))
    elif a.cmd == "send":
        out(send_mail(a.to, a.subject, a.body, a.cc))
    elif a.cmd == "calendars":
        out(list_calendars())
    elif a.cmd == "events":
        out(list_events(a.calendar, a.start, a.end))
    elif a.cmd == "create-event":
        out(create_event(a.calendar, a.summary, a.start, a.end, a.desc, a.location, a.attendee))
    elif a.cmd == "delete-event":
        out(delete_event(a.calendar, a.uid))
    elif a.cmd == "contacts":
        out(list_contacts())


if __name__ == "__main__":
    main()
