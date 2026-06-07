#!/usr/bin/env python3
"""Fetch the day's notable Hacker News stories + their top comments as JSON.

Pulls from the official Hacker News Firebase API (no auth needed), keeps stories
inside a recency window, ranks them, and for each fetches the top-voted comment
threads. The output is a compact JSON bundle the agent then summarizes into a
digest. Stdlib only (urllib / html.parser / concurrent.futures).

Usage:
    hackernews.py digest [--view top|best|new|ask|show] [--limit 8]
                         [--comments 8] [--since-hours 30] [--fetch 80]
                         [--sort score|comments|new]
                         [--max-post-chars 6000] [--max-comment-chars 1200]

Notes on views (these map to the API's story lists):
    top    current front-page ranking (default)
    best   highest-scoring recent stories
    new    newest submissions first
    ask    Ask HN posts
    show   Show HN posts

The API exposes no per-comment score, so "top comments" are the story's
top-level threads in HN's own ranked order (the first N children).
"""
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

API = "https://hacker-news.firebaseio.com/v0"
ITEM_URL = "https://news.ycombinator.com/item?id=%s"
UA = "Mozilla/5.0 (compatible; hacker-news-digest/1.0)"

VIEWS = {
    "top": "topstories",
    "best": "beststories",
    "new": "newstories",
    "ask": "askstories",
    "show": "showstories",
}


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        die(f"Hacker News API request failed: {e}")
    except json.JSONDecodeError as e:
        die(f"Hacker News API returned invalid JSON: {e}")


def get_item(item_id):
    # Individual item fetch; tolerate a single failed/null item rather than
    # aborting the whole run.
    req = urllib.request.Request(f"{API}/item/{item_id}.json", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


def get_items(ids, workers=16):
    if not ids:
        return []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(get_item, ids))


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "blockquote", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_entityref(self, name):
        self.parts.append({"amp": "&", "lt": "<", "gt": ">", "quot": '"',
                           "#x27": "'", "#x2F": "/"}.get(name, ""))

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


def iso(ts):
    if not ts:
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def cmd_digest(args):
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=args.since_hours)
    cutoff_ts = cutoff.timestamp()

    list_url = f"{API}/{VIEWS[args.view]}.json"
    ids = get_json(list_url) or []
    ids = ids[: args.fetch]

    raw = [it for it in get_items(ids) if it and it.get("type") in ("story", "job")]

    # Keep stories inside the recency window.
    posts = [p for p in raw if (p.get("time") or 0) >= cutoff_ts]

    # If the window filtered everything out (slow day / odd clock), fall back to
    # the unfiltered list so the digest is never empty.
    windowed = bool(posts)
    if not posts:
        posts = list(raw)

    keyfn = {
        "score": lambda p: (p.get("score") or 0),
        "comments": lambda p: (p.get("descendants") or 0),
        "new": lambda p: (p.get("time") or 0),
    }[args.sort]
    posts.sort(key=keyfn, reverse=True)
    posts = posts[: args.limit]

    out_posts = []
    for p in posts:
        body = html_to_text(p.get("text"))  # self/Ask/Show posts; link posts have none
        comments = []
        kid_ids = (p.get("kids") or [])[: args.comments]
        if args.comments > 0 and kid_ids:
            for c in get_items(kid_ids):
                if not c or c.get("deleted") or c.get("dead"):
                    continue
                txt = html_to_text(c.get("text"))
                if not txt.strip():
                    continue
                comments.append({
                    "author": c.get("by") or "—",
                    "score": None,  # HN API exposes no per-comment score
                    "text": truncate(txt, args.max_comment_chars),
                })
        out_posts.append({
            "title": p.get("title"),
            "author": p.get("by") or "—",
            "url": p.get("url") or (ITEM_URL % p.get("id")),
            "hn_url": ITEM_URL % p.get("id"),
            "score": p.get("score"),
            "comment_count": p.get("descendants"),
            "posted_at": iso(p.get("time")),
            "body": truncate(body, args.max_post_chars),
            "top_comments": comments,
        })

    print(json.dumps({
        "source": "hackernews",
        "generated_at": now.isoformat(),
        "view": args.view,
        "sort": args.sort,
        "window_hours": args.since_hours,
        "windowed": windowed,
        "count": len(out_posts),
        "posts": out_posts,
    }, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Hacker News daily digest fetcher")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="fetch ranked recent stories + top comments")
    d.add_argument("--view", default="top", choices=list(VIEWS))
    d.add_argument("--limit", type=int, default=8, help="number of stories to include")
    d.add_argument("--comments", type=int, default=8, help="top comment threads per story")
    d.add_argument("--since-hours", type=int, default=30,
                   help="only include stories newer than this many hours")
    d.add_argument("--fetch", type=int, default=80,
                   help="how many stories to pull from the view before filtering")
    d.add_argument("--sort", default="score", choices=["score", "comments", "new"])
    d.add_argument("--max-post-chars", type=int, default=6000)
    d.add_argument("--max-comment-chars", type=int, default=1200)
    args = ap.parse_args()

    if args.cmd == "digest":
        cmd_digest(args)


if __name__ == "__main__":
    main()
