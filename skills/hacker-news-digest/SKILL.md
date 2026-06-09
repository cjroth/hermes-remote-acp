---
name: hacker-news-digest
description: "Build a readable Hacker News digest: fetch the day's top/trending stories plus their top comment threads and summarize each story and its discussion, opening with an overall summary of the day. Produces the digest only — delivery (email, etc.) is a separate step the user requests. Use when asked for a Hacker News / HN digest/roundup."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [HackerNews, Digest, Summary, News, Tech]
---

# Hacker News daily digest

Produce a single, readable digest of the day on **Hacker News**: the most
notable recent stories and what people are saying in the comments. It opens with
a short **overall summary of the day**, then gives a **per-story summary** (story
+ its discussion).

This skill **only builds the digest** — it does not send or deliver it. Output
the finished digest in the conversation and stop there. Delivery is decoupled:
if the user wants it emailed, they'll ask, and that's the `email-me` skill's job.
This mirrors the `lesswrong-digest` skill — same shape, same output format — so
the two read uniformly when delivered side by side.

Pipeline: `hackernews.py` (fetch) → you (summarize) → done.

## 1. Fetch the material

```bash
python3 scripts/hackernews.py digest --limit 8 --comments 6 --since-hours 30
```

The defaults are tuned to keep the fetch payload lean — ~6 comment threads per
story, trimmed lengths — because the digest only needs 1–3 sentences of
discussion per story, so pulling 8 full comments wastes context. Bump
`--comments` / `--max-comment-chars` if you specifically want more depth.

This hits the official Hacker News Firebase API (no auth) and returns JSON with
the day's ranked stories; each entry has `title`, `author`, `url` (the linked
article, or the HN thread for text posts), `hn_url` (always the HN discussion),
`score`, `comment_count`, `posted_at`, `body` (post text — present only for
Ask/Show/self posts; link posts have none), and `top_comments` (`author`,
`score`, `text`). Useful flags:

- `--view top|best|new|ask|show` — `top` (default) is the current front-page
  ranking; `best` is highest-scoring recent stories; `new` is newest first;
  `ask`/`show` restrict to Ask HN / Show HN.
- `--sort score|comments|new` — default `score` surfaces the most notable; use
  `comments` to favor the liveliest discussions.
- `--since-hours N` — recency window (default 30 ≈ "that day"). If nothing falls
  in the window the script falls back to the latest stories and sets
  `"windowed": false` — mention that the day was quiet if so.
- `--limit` / `--comments` — how many stories, and how many top comment threads
  per story.

**On comments:** the HN API exposes no per-comment score, so `top_comments` are
the story's top-level threads in HN's own ranked order (the first N children),
and each comment's `score` is `null`. Treat their order as the signal.

## 2. Summarize

Write the digest from the JSON. Structure it exactly so the operator can read
top-down (identical to the LessWrong digest):

1. **Overall summary** (3–6 sentences): the themes of the day, what's getting
   the most attention/debate, anything notable. This goes first.
2. **Per-story sections**, in the JSON's order. For each story:
   - Title (linked to `url`), author, score, and comment count. When `url` is an
     external article, also link the HN discussion via `hn_url` ("[discussion]").
   - 2–4 sentences summarizing the **story** itself. For link posts there's no
     `body`, so lean on the title and the comments to convey what it's about.
   - 1–3 sentences on the **discussion** — the main threads, agreements,
     pushback, or notable points from `top_comments`. Skip if there are none.

Guidance: be concrete and neutral; summarize arguments, don't editorialize.
Attribute notable comment points to their author when it helps. If a post body
is truncated (`[…]`), summarize what's present and lean on the title/comments.

That's the whole job — present the digest and stop. Don't email it unless the
user asks; if they do, hand the finished digest to the `email-me` skill.
