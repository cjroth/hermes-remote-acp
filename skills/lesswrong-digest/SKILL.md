---
name: lesswrong-digest
description: "Build a readable LessWrong digest: fetch the day's top/trending posts plus their top comments and summarize each post and its discussion, opening with an overall summary of the day. Produces the digest only — delivery (email, etc.) is a separate step the user requests. Use when asked for a LessWrong digest/roundup."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [LessWrong, Digest, Summary, Research]
---

# LessWrong daily digest

Produce a single, readable digest of the day on **LessWrong**: the most notable
recent posts and what people are saying in the comments. It opens with a short
**overall summary of the day**, then gives a **per-post summary** (post + its
discussion).

This skill **only builds the digest** — it does not send or deliver it. Output
the finished digest in the conversation and stop there. Delivery is decoupled:
if the user wants it emailed, they'll ask, and that's the `email-me` skill's job.
This mirrors the `hacker-news-digest` skill — same shape, same output format — so
the two read uniformly when delivered side by side.

Pipeline: `lesswrong.py` (fetch) → you (summarize) → done.

## 1. Fetch the material

```bash
python3 scripts/lesswrong.py digest --limit 8 --comments 8 --since-hours 30
```

This returns JSON with the day's ranked posts; each entry has `title`, `author`,
`url`, `score`, `comment_count`, `posted_at`, `body` (post text, truncated), and
`top_comments` (`author`, `score`, `text`). Useful flags:

- `--view new|magic|top` — `new` (default, then filtered to the window and
  ranked) captures *today's* posts; `magic` is LessWrong's trending order.
- `--sort score|comments|new` — default `score` surfaces the most notable;
  use `comments` to favor the liveliest discussions.
- `--since-hours N` — recency window (default 30 ≈ "that day"). If nothing falls
  in the window the script falls back to the latest posts and sets
  `"windowed": false` — mention that the day was quiet if so.
- `--limit` / `--comments` — how many posts, and how many top comments per post.

## 2. Summarize

Write the digest from the JSON. Structure it exactly so the operator can read
top-down:

1. **Overall summary** (3–6 sentences): the themes of the day, what's getting
   the most attention/debate, anything notable. This goes first.
2. **Per-post sections**, in the JSON's order. For each post:
   - Title (linked to `url`), author, score, and comment count.
   - 2–4 sentences summarizing the **post** itself.
   - 1–3 sentences on the **discussion** — the main threads, agreements,
     pushback, or notable points from `top_comments`. Skip if there are none.

Guidance: be concrete and neutral; summarize arguments, don't editorialize.
Attribute notable comment points to their author when it helps. If a post body
is truncated (`[…]`), summarize what's present and lean on the title/comments.

That's the whole job — present the digest and stop. Don't email it unless the
user asks; if they do, hand the finished digest to the `email-me` skill.
