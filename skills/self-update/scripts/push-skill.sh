#!/bin/sh
# push-skill.sh — commit edited skills from the /data/repo working tree to
# GitHub (main) and refresh them into the live skills dir for this session.
#
# Usage:
#   push-skill.sh "<commit message>" [<skill-name> ...]
#
# With skill names, stages only those skills (skills/<name>). Without, stages
# every change currently under skills/. Either way it NEVER stages anything
# outside skills/ — infra edits (Dockerfile, init.sh, ...) are deliberately
# out of scope and must go through a normal PR.
set -eu

REPO_DIR="${REPO_DIR:-/data/repo}"
LIVE_SKILLS="${LIVE_SKILLS:-/data/hermes/skills}"

fail() { echo "error: $*" >&2; exit 1; }

[ -n "${1:-}" ] || fail 'missing commit message — usage: push-skill.sh "<message>" [<skill-name> ...]'
MSG="$1"; shift

[ -n "${GITHUB_TOKEN:-}" ] || fail "GITHUB_TOKEN is not set — self-update is not enabled on this deployment"
[ -d "$REPO_DIR/.git" ] || fail "$REPO_DIR is not a git clone — self-update is not enabled (see init.sh)"

cd "$REPO_DIR"

# Stage only under skills/. Restricting the pathspec is what keeps this from
# ever committing core stack files, even though the token technically could.
if [ "$#" -gt 0 ]; then
    for name in "$@"; do
        [ -d "skills/$name" ] || fail "no such skill: skills/$name"
        git add -A -- "skills/$name"
    done
else
    git add -A -- skills/
fi

# Nothing staged? Then there was nothing to do.
if git diff --cached --quiet -- skills/; then
    echo "nothing to commit under skills/ — did you edit files in $REPO_DIR/skills/ ?"
    exit 0
fi

git commit -q -m "$MSG"
echo "committed: $(git rev-parse --short HEAD) $MSG"

if git push -q origin HEAD:main; then
    echo "pushed to origin/main"
else
    fail "push failed — check the token has Contents: write on this repo and main isn't protected"
fi

# Refresh the live copy so the change is active in this session too. Map each
# flat repo skill (skills/<name>) to its live category path by finding where it
# already lives under $LIVE_SKILLS; fall back to skills/<name> if it's new.
refresh_one() {
    name="$1"
    src="$REPO_DIR/skills/$name"
    [ -d "$src" ] || return 0
    existing="$(find "$LIVE_SKILLS" -mindepth 2 -maxdepth 2 -type d -name "$name" 2>/dev/null | head -n1)"
    if [ -n "$existing" ]; then
        dest="$existing"
    else
        dest="$LIVE_SKILLS/skills/$name"
    fi
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    cp -rf "$src" "$dest"
    echo "refreshed live: $dest"
}

if [ "$#" -gt 0 ]; then
    for name in "$@"; do refresh_one "$name"; done
else
    # Refresh whatever changed in this commit under skills/.
    git show --name-only --pretty=format: HEAD -- skills/ \
        | sed -n 's#^skills/\([^/]*\)/.*#\1#p' | sort -u \
        | while read -r name; do [ -n "$name" ] && refresh_one "$name"; done
fi

echo "done — change is live now; other machines pick it up on their next boot/deploy"
