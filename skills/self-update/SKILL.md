---
name: self-update
description: "Edit the agent's own skills and push the changes back to the c-stack GitHub repo (main), so improvements persist across redeploys and propagate to every machine. Use when you've improved a skill (fixed a bug, refined instructions, added a helper) and want that change to stick rather than be lost on the next reboot."
version: 1.0.0
author: community
license: MIT
platforms: [linux]
prerequisites:
  env_vars: [GITHUB_TOKEN]
metadata:
  hermes:
    tags: [SelfUpdate, Skills, Git, GitHub, Persistence]
---

# Self-update

Lets you improve your **own skills** and have those improvements persist. Skill
edits made to the live skills dir (`/data/hermes/skills/...`) are **wiped on
every reboot** — the boot script regenerates that dir from the source repo. So
the only way an edit survives is to push it back to GitHub. This skill is that
path: edit in the working tree, then commit + push to `main`.

## The mental model

There are two copies of every skill on this machine:

| Location | Role |
|----------|------|
| `/data/repo/skills/<name>/` | **Working tree** — a git clone of the source repo. Edit here. |
| `/data/hermes/skills/<category>/<name>/` | **Live copy** — what's actually loaded. Regenerated from the working tree on every boot. **Never edit here directly; it's overwritten.** |

The loop:

```
edit /data/repo/skills/<name>  →  push-skill.sh  →  commit + push to main
   ↓                                                        ↓
refresh live copy (active now)            other machines pull on next boot/deploy
```

A pushed change goes live **on this machine** immediately (the script refreshes
the live copy), and on **every other machine** the next time it boots — i.e.
after `fly deploy` or `fly apps restart`. No image rebuild is needed for skill
edits.

## How to use it

1. **Edit the skill in the working tree**, not the live copy:

   ```
   /data/repo/skills/<name>/SKILL.md      (and scripts/, etc.)
   ```

   Find the working tree with `ls /data/repo/skills/`. If `/data/repo` doesn't
   exist, self-update isn't enabled on this deployment (no `GITHUB_TOKEN`) —
   stop and tell the operator.

2. **Commit + push** with the helper:

   ```sh
   /data/hermes/skills/system/self-update/scripts/push-skill.sh \
       "Tighten lesswrong-digest comment ranking" lesswrong-digest
   ```

   First argument is the commit message. The remaining arguments are the skill
   names you changed (omit them to commit everything currently changed under
   `skills/`). The script:
   - stages **only paths under `skills/`** (it will never commit `Dockerfile`,
     `init.sh`, or other core files — keep skill edits and infra edits separate);
   - commits and pushes to `main`;
   - copies the new version into the live skills dir so it's active in this
     session.

3. **Confirm** the script printed the pushed commit hash. If the push failed
   (e.g. token lacks Contents: write, or the branch is protected), it says so —
   relay that to the operator rather than retrying blindly.

## Scope and limits

- **Editing existing skills only.** Creating a brand-new skill that survives a
  full image rebuild also needs a `COPY` line in the `Dockerfile` and an entry
  in the `init.sh` refresh loop — that's a normal code change, not something
  this skill does. (A new skill pushed via this skill will live on the current
  machine but won't be baked into the image until those entries are added.)
- **`main` directly.** This pushes straight to `main` — there is no review gate
  before the push. The operator's review happens at deploy time. Make focused,
  well-described commits.
- **Skills only.** The helper refuses to stage anything outside `skills/`. If
  you need to change core stack files, do that as a normal edit + PR, not here.
