#!/usr/bin/env python3
"""Fetch the day's notable LessWrong posts + their top comments as JSON.

Pulls from the LessWrong GraphQL API (no auth needed), keeps posts inside a
recency window, ranks them, and for each fetches the top-voted comments. The
output is a compact JSON bundle the agent then summarizes into a digest email.
Stdlib only (urllib / html.parser).

Usage:
    lesswrong.py digest [--view new|magic|top] [--limit 8] [--comments 8]
                        [--since-hours 30] [--fetch 60]
                        [--sort score|comments|new]
                        [--max-post-chars 6000] [--max-comment-chars 1200]

Notes on views:
    new    newest posts first (default; we then filter to the window and rank)
    magic  LessWrong's "hot"/trending ordering
    top    highest karma all-time (combine with a small --since-hours carefully)
"""
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

API = "https://www.lesswrong.com/graphql"
UA = "Mozilla/5.0 (compatible; lesswrong-digest/1.0)"


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def gql(query):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        die(f"LessWrong API request failed: {e}")
    if "errors" in payload and payload["errors"]:
        die(f"GraphQL error: {payload['errors'][0].get('message', payload['errors'])}")
    return payload.get("data", {})


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "blockquote", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def text(self):
        out = "".join(self.parts)
        # collapse runs of blank lines / trailing whitespace
        lines = [ln.rstrip() for ln in out.splitlines()]
        cleaned, blanks = [], 0
        for ln in lines:
            if ln.strip() == "":
                blanks += 1
                if blanks <= 1:
                    cleaned.append("")
            else:
                blanks = 0
                cleaned.append(ln)
        return "\n".join(cleaned).strip()


def html_to_text(html):
    if not html:
        return ""
    p = _Stripper()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - never let a malformed post break the run
        return ""
    return p.text()


def truncate(s, n):
    if not s:
        return ""
    return s if len(s) <= n else s[:n].rstrip() + " […]"


def parse_dt(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_posts(view, fetch):
    q = """
    { posts(input: {terms: {view: "%s", limit: %d}}) { results {
        _id title pageUrl postedAt baseScore commentCount
        user { displayName }
        contents { wordCount html plaintextDescription }
    } } }
    """ % (view, fetch)
    data = gql(q)
    return ((data.get("posts") or {}).get("results")) or []


def fetch_comments(post_id, limit):
    q = """
    { comments(input: {terms: {view: "postCommentsTop", postId: "%s", limit: %d}}) {
        results { baseScore user { displayName } contents { plaintextMainText } }
    } }
    """ % (post_id, limit)
    data = gql(q)
    return ((data.get("comments") or {}).get("results")) or []


def cmd_digest(args):
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=args.since_hours)

    raw = fetch_posts(args.view, args.fetch)

    posts = []
    for p in raw:
        posted = parse_dt(p.get("postedAt"))
        if posted is not None and posted < cutoff:
            continue
        posts.append(p)

    # If the window filtered everything out (slow day / odd clock), fall back to
    # the unfiltered view so the digest is never empty.
    windowed = bool(posts)
    if not posts:
        posts = list(raw)

    keyfn = {
        "score": lambda p: (p.get("baseScore") or 0),
        "comments": lambda p: (p.get("commentCount") or 0),
        "new": lambda p: (p.get("postedAt") or ""),
    }[args.sort]
    posts.sort(key=keyfn, reverse=True)
    posts = posts[: args.limit]

    out_posts = []
    for p in posts:
        contents = p.get("contents") or {}
        body = html_to_text(contents.get("html")) or (contents.get("plaintextDescription") or "")
        comments = []
        if args.comments > 0 and (p.get("commentCount") or 0) > 0:
            for c in fetch_comments(p["_id"], args.comments):
                txt = ((c.get("contents") or {}).get("plaintextMainText")) or ""
                if not txt.strip():
                    continue
                comments.append({
                    "author": ((c.get("user") or {}).get("displayName")) or "—",
                    "score": c.get("baseScore"),
                    "text": truncate(txt, args.max_comment_chars),
                })
        out_posts.append({
            "title": p.get("title"),
            "author": ((p.get("user") or {}).get("displayName")) or "—",
            "url": p.get("pageUrl"),
            "score": p.get("baseScore"),
            "comment_count": p.get("commentCount"),
            "posted_at": p.get("postedAt"),
            "word_count": contents.get("wordCount"),
            "body": truncate(body, args.max_post_chars),
            "top_comments": comments,
        })

    print(json.dumps({
        "source": "lesswrong",
        "generated_at": now.isoformat(),
        "view": args.view,
        "sort": args.sort,
        "window_hours": args.since_hours,
        "windowed": windowed,
        "count": len(out_posts),
        "posts": out_posts,
    }, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="LessWrong daily digest fetcher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="fetch ranked recent posts + top comments")
    d.add_argument("--view", default="new", choices=["new", "magic", "top"])
    d.add_argument("--limit", type=int, default=8, help="number of posts to include")
    d.add_argument("--comments", type=int, default=6, help="top comments per post")
    d.add_argument("--since-hours", type=int, default=30,
                   help="only include posts newer than this many hours")
    d.add_argument("--fetch", type=int, default=60,
                   help="how many posts to pull from the view before filtering")
    d.add_argument("--sort", default="score", choices=["score", "comments", "new"])
    d.add_argument("--max-post-chars", type=int, default=5000)
    d.add_argument("--max-comment-chars", type=int, default=800)
    args = ap.parse_args()

    if args.cmd == "digest":
        cmd_digest(args)


if __name__ == "__main__":
    main()
