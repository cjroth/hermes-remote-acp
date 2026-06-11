#!/bin/sh
# Single entrypoint that orchestrates tailscaled + tailnet serve + the bridge,
# WITHOUT s6-overlay. s6 requires PID 1, which Fly.io's init doesn't give it
# (it crash-loops with "can only run as pid 1"). This script needs no special
# PID, so it runs anywhere — Fly (kernel TUN) and other hosts (userspace).
set -e

SOCK=/var/run/tailscale/tailscaled.sock
HOSTNAME="${TS_HOSTNAME:-hermes}"
PORT=8443
TS="/usr/local/bin/tailscale --socket=$SOCK"

mkdir -p /var/run/tailscale /data/tailscale /dev/net /run/tls

# One persistent volume at /data holds everything that must survive restarts:
#   /data/vault     = the ASP-synced vault. HERMES_HOME lives INSIDE it at
#                     /data/vault/agents/hermes, so the agent's context
#                     (memories/, SOUL.md, config.yaml, skills/, cron/, work
#                     products) syncs to the hub alongside the operator's
#                     notes. Machine-local state is excluded by the vault-root
#                     .aspignore seeded in the ASP block below.
#   /data/asp       = ASP device identity + sync log (never synced)
#   /data/tailscale = tailscaled state (node identity + TLS cert)
HERMES_HOME=/data/vault/agents/hermes

# One-time migration from the pre-ASP layout: move /data/hermes into the vault.
# The old vault is backed up first (it's small — mostly markdown) because the
# initial `asp clone` materializes the hub's copy over untracked same-path
# files. A symlink keeps the old /data/hermes path working for anything that
# hardcoded it. Dead CSP state (/data/vault/.context) is dropped — ASP ignores
# that dir anyway, the old CSP remote is gone, and the backup keeps a copy.
if [ -d /data/hermes ] && [ ! -L /data/hermes ] && [ ! -e "$HERMES_HOME" ]; then
    echo "[init] migrating /data/hermes -> $HERMES_HOME" >&2
    if [ -d /data/vault ] && [ ! -e /data/vault-pre-asp.bak ]; then
        cp -a /data/vault /data/vault-pre-asp.bak || \
            echo "[init] WARN: vault backup failed; continuing" >&2
    fi
    mkdir -p /data/vault/agents
    mv /data/hermes "$HERMES_HOME"
    rm -rf /data/vault/.context
fi
mkdir -p "$HERMES_HOME"
ln -sfn "$HERMES_HOME" /data/hermes

# Fly mounts /data root-owned, so hand the vault + hermes home to the hermes
# user (top levels only; the trees keep their existing ownership), then
# (re)seed config.yaml from the image (repo is the source of truth for the
# model/provider; runtime data persists alongside it). config.yaml sits in the
# synced vault, so the seeded copy is also visible on every other device.
chown hermes:hermes /data/vault /data/vault/agents "$HERMES_HOME" 2>/dev/null || true
install -o hermes -g hermes -m 644 /opt/seed/config.yaml "$HERMES_HOME/config.yaml" 2>/dev/null || \
    cp /opt/seed/config.yaml "$HERMES_HOME/config.yaml"

# --- Clean rebuildable package caches from the volume on every boot -----------
# These are download caches for npm, bun, rustup, and uv. They regenerate
# automatically on next use (npm install, bun install, rustup install, uv pip
# install) and would otherwise bloat the persistent volume over time with no
# benefit — they only speed up repeat installs, which are rare at runtime.
rm -rf /data/hermes/.npm/_cacache \
       /data/hermes/.bun/install/cache \
       /data/hermes/.rustup/downloads \
       /data/hermes/.cache/uv

# --- Self-update: source repo working tree ------------------------------------
# When GITHUB_TOKEN is set, keep a git clone of the source repo at /data/repo
# (on the persistent volume). It's the working tree the `self-update` skill
# commits from, AND the source for the skill refresh below — so a skill change
# pushed to main goes live on any machine's next boot WITHOUT an image rebuild
# (just `fly deploy` / `fly apps restart`). Unset ⇒ skills come from the image
# as before. The token is NOT written to .git/config or baked into the remote
# URL: init-time fetch/clone use a transient in-memory auth URL, and the agent's
# own pushes read the token from a mode-600 file (/data/.gh_token) via a
# credential helper. (Why a file, not the env var: GITHUB_TOKEN reaches the
# Hermes *daemon* but does NOT propagate into the agent's tool/shell subprocess,
# so a $GITHUB_TOKEN-based helper resolves to empty and pushes fail with
# "Invalid username or token" — the file is read at push time regardless.)
REPO_DIR=/data/repo
if [ -n "${GITHUB_TOKEN:-}" ]; then
    if command -v git >/dev/null 2>&1; then
        GITHUB_REPO="${GITHUB_REPO:-cjroth/c-stack}"
        PLAIN_URL="https://github.com/${GITHUB_REPO}.git"
        AUTH_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
        export GITHUB_TOKEN  # used by the init-time fetch/clone auth URL below
        # Stash the token in a mode-600 file the push credential helper cat's at
        # push time. Required because the agent's tool/shell subprocess does NOT
        # inherit GITHUB_TOKEN (it reaches the daemon, not shell tools), so a
        # $GITHUB_TOKEN-based helper would resolve to empty. Lives OUTSIDE
        # $REPO_DIR so it can never be committed/pushed.
        ( umask 077; printf '%s' "$GITHUB_TOKEN" > /data/.gh_token )
        chown hermes:hermes /data/.gh_token 2>/dev/null || true
        chmod 600 /data/.gh_token 2>/dev/null || true
        if [ -d "$REPO_DIR/.git" ]; then
            su hermes -c "cd '$REPO_DIR' && git fetch --quiet '$AUTH_URL' main && git reset --hard --quiet FETCH_HEAD" \
                >>/data/repo.log 2>&1 || echo "[init] WARN: repo pull failed (see /data/repo.log)" >&2
        else
            chown hermes:hermes "$(dirname "$REPO_DIR")" 2>/dev/null || true
            su hermes -c "git clone --quiet '$AUTH_URL' '$REPO_DIR'" \
                >>/data/repo.log 2>&1 || echo "[init] WARN: repo clone failed (see /data/repo.log)" >&2
        fi
        if [ -d "$REPO_DIR/.git" ]; then
            # Strip the token from origin, set commit identity + a credential
            # helper that reads the token from /data/.gh_token at push time.
            su hermes -c "git -C '$REPO_DIR' remote set-url origin '$PLAIN_URL'; \
                git -C '$REPO_DIR' config user.name '${GIT_USER_NAME:-hermes-agent}'; \
                git -C '$REPO_DIR' config user.email '${GIT_USER_EMAIL:-${USER_PRIMARY_EMAIL:-hermes@localhost}}'; \
                git -C '$REPO_DIR' config credential.helper '!f() { echo username=x-access-token; echo password=\$(cat /data/.gh_token); }; f'" \
                >>/data/repo.log 2>&1 || true
        fi
    else
        echo "[init] WARN: GITHUB_TOKEN set but git not installed; self-update disabled" >&2
    fi
fi

# Refresh the bundled skills into the writable skills dir on every boot. The
# skill loader seeds bundled skills only when ABSENT, so without this an updated
# skill would never reach $HERMES_HOME/skills after the first deploy. Prefer the
# /data/repo working tree (so pushed skill edits propagate on restart); fall
# back to the image-baked copy when the clone is absent. Either way the live
# copy is overwritten, so the source (repo > image) stays authoritative.
# Each entry is "<category>/<skill>"; the basename matches the flat repo path.
for skill in communication/proton communication/email-me research/lesswrong-digest research/hacker-news-digest personal/goals personal/prospector personal/event-prospector system/self-update; do
    name="$(basename "$skill")"
    if [ -d "$REPO_DIR/skills/$name" ]; then
        src="$REPO_DIR/skills/$name"
    else
        src="/opt/hermes/skills/$skill"
    fi
    [ -d "$src" ] || continue
    dest_dir="$HERMES_HOME/skills/$(dirname "$skill")"
    mkdir -p "$dest_dir"
    rm -rf "$dest_dir/$name"
    cp -rf "$src" "$dest_dir/"
    chown -R hermes:hermes "$dest_dir/$name" 2>/dev/null || true
done

# Notion: the `ntn` CLI and the bundled `notion` skill read NOTION_API_TOKEN;
# alias it from the NOTION_API_KEY secret so the agent uses the CLI path. Both
# the gateway and the bridge (→ hermes-acp) inherit this exported env.
if [ -n "${NOTION_API_KEY:-}" ]; then
    export NOTION_API_TOKEN="$NOTION_API_KEY"
fi

# --- tailscaled: requires a real kernel TUN device ---------------------------
# We deliberately do NOT fall back to userspace networking: its software net
# stack stalls TLS handshakes (5-30s connects that wedge after a couple). So we
# require kernel TUN and fail loudly if the host forbids it (many PaaS do). Run
# on a TUN-capable host (Fly.io VMs, a VPS, etc.).
[ -c /dev/net/tun ] || mknod /dev/net/tun c 10 200 2>/dev/null || true
if [ ! -c /dev/net/tun ]; then
    echo "[init] FATAL: no /dev/net/tun. This needs a TUN-capable host (Fly.io VM, VPS, …)." >&2
    echo "[init] Userspace-networking Tailscale stalls TLS handshakes; refusing to run in it." >&2
    exit 1
fi
echo "[init] kernel TUN mode" >&2
/usr/local/bin/tailscaled --statedir=/data/tailscale --socket="$SOCK" >/tmp/tailscaled.log 2>&1 &

# --- join tailnet + expose the bridge to the tailnet only --------------------
# Done in the background so a transient failure never blocks the bridge.
(
  i=0; while [ ! -S "$SOCK" ] && [ "$i" -lt 30 ]; do i=$((i+1)); sleep 1; done

  if [ -z "${TS_AUTHKEY:-}" ]; then
      echo "[init] TS_AUTHKEY unset — not joining tailnet" >&2; exit 0
  fi

  echo "[init] joining tailnet as '$HOSTNAME'..." >&2
  $TS up --authkey="$TS_AUTHKEY" --hostname="$HOSTNAME" --accept-routes=false || {
      echo "[init] tailscale up failed" >&2; exit 0; }

  # Self FQDN = first <label>.<tailnet>.ts.net match (bare suffix won't match).
  FQDN=""; j=0
  while [ -z "$FQDN" ] && [ "$j" -lt 60 ]; do
      FQDN=$($TS status --json 2>/dev/null | grep -oE '[A-Za-z0-9-]+\.[A-Za-z0-9-]+\.ts\.net' | head -1)
      [ -z "$FQDN" ] && { j=$((j+1)); sleep 1; }
  done

  echo "[init] provisioning TLS cert for ${FQDN:-<unknown>}..." >&2
  ok=""
  if [ -n "$FQDN" ]; then
      c=0; while [ "$c" -lt 12 ]; do
          if $TS cert --cert-file /run/tls/tls.crt --key-file /run/tls/tls.key "$FQDN" >/dev/null 2>/tmp/cert.err; then ok=1; break; fi
          c=$((c+1)); sleep 5
      done
  fi
  $TS serve reset >/dev/null 2>&1 || true
  if [ -n "$ok" ]; then
      chmod 644 /run/tls/tls.crt /run/tls/tls.key 2>/dev/null || true
      # Raw TCP passthrough: tailnet :443 -> bridge WSS on 127.0.0.1:8443.
      # (Bridge terminates TLS; Tailscale just forwards bytes.)
      $TS serve --bg --tcp=443 tcp://127.0.0.1:$PORT >/dev/null 2>&1
      echo "[init] serving wss://$FQDN/" >&2
  else
      echo "[init] cert unavailable ($(tr '\n' ' ' </tmp/cert.err 2>/dev/null)) — plain ws on :80" >&2
      $TS serve --bg --http=80 "http://127.0.0.1:$PORT" >/dev/null 2>&1
  fi
) &

# --- Matrix (Beeper) gateway (optional, runs as hermes user, background) -------
# `hermes gateway run` serves the Matrix platform, auto-enabled from
# MATRIX_ACCESS_TOKEN (gateway _apply_env_overrides) — no interactive
# `gateway setup` needed. MATRIX_HOMESERVER points at Beeper
# (https://matrix.beeper.com). Outbound-only, so unaffected by the tailnet-only
# lockdown. Runs as a supervised BACKGROUND process; the ACP bridge stays the
# foreground PID below — so ACP and the Matrix gateway coexist and both stay
# usable. State (sessions, Matrix E2EE crypto store) lives in HERMES_HOME on
# the persistent volume (the E2EE store is .aspignore'd — device-bound keys
# must never replicate to another machine).
if [ -n "${MATRIX_ACCESS_TOKEN:-}" ]; then
    # E2EE crypto store + device identity must survive restarts, so keep them on
    # the volume (Hermes' default store path under HERMES_HOME). Pre-create it
    # owned by hermes since the gateway runs de-privileged; losing this dir means
    # losing the bot's encryption identity (see matrix.md E2EE notes).
    mkdir -p "$HERMES_HOME/platforms/matrix/store"
    chown -R hermes:hermes "$HERMES_HOME/platforms" 2>/dev/null || true
    [ -n "${MATRIX_HOMESERVER:-}" ] || \
      echo "[init] WARN: MATRIX_ACCESS_TOKEN set but MATRIX_HOMESERVER unset (Beeper = https://matrix.beeper.com)" >&2
    echo "[init] starting Matrix gateway (hermes user, supervised)..." >&2
    # Supervised respawn loop: the gateway is a plain background process (no s6 /
    # systemd here), so if it ever exits — crash, OOM, or the agent stopping it —
    # nothing would restart it and it'd stay dead until the next machine reboot.
    # This loop respawns it (5s backoff) so the bot self-heals. Each respawn is
    # logged. A clean config won't loop; a bad one logs every 5s (visible).
    (
      while true; do
        HOME="$HERMES_HOME" HERMES_HOME="$HERMES_HOME" \
          /command/s6-setuidgid hermes /opt/hermes/.venv/bin/hermes gateway run \
          >>"$HERMES_HOME/gateway.log" 2>&1
        echo "[init] Matrix gateway exited (code $?); respawning in 5s..." >>"$HERMES_HOME/gateway.log"
        sleep 5
      done
    ) &
else
    echo "[init] MATRIX_ACCESS_TOKEN unset — Matrix gateway not started" >&2
fi

# --- ASP vault + agent-context sync (optional, hermes user, background) -------
# Keeps /data/vault (on the persistent volume) synced with the remote ASP hub
# via the `asp` CLI: clone on the first boot, then `asp watch --peer` on every
# boot after. HERMES_HOME lives inside the vault, so this syncs the agent's
# context — memories/, SOUL.md, config.yaml, skills/, cron/, loose work
# products — along with the operator's notes. The vault-root .aspignore seeded
# below keeps machine-local state (live SQLite DBs, caches, toolchains, logs,
# secrets, the device-bound Matrix E2EE store) out of the sync.
#
# Auth is ASP's enrollment model: ASP_AUTH_KEY is a pre-shared bearer secret
# (read directly by `asp` from the env) sent on the WS upgrade; the hub
# accepts it and durably authorizes THIS node's own ed25519 key. The identity
# persists at ASP_HOME=/data/asp (on the volume, never synced) so it stays
# stable across restarts. Reverse trust (this node trusting the hub) is
# bootstrapped by `clone` via trust-on-first-use.
#   ASP_AUTH_KEY = pre-shared enrollment secret. REQUIRED; unset ⇒ skipped.
#   ASP_REMOTE   = hub URL (wss://host[:port], or ws://… if plaintext) —
#                  set in fly.toml [env]; the auth key is a Fly secret.
if [ -z "${ASP_AUTH_KEY:-}" ]; then
    echo "[init] ASP_AUTH_KEY unset — no auth key set; ASP vault sync not started" >&2
elif [ -z "${ASP_REMOTE:-}" ]; then
    echo "[init] ASP_REMOTE unset — no remote to connect to; ASP vault sync not started" >&2
else
    echo "[init] starting ASP vault sync (hermes user, supervised) → $ASP_REMOTE" >&2
    mkdir -p /data/asp
    chown -R hermes:hermes /data/asp 2>/dev/null || true
    chown hermes:hermes /data/vault 2>/dev/null || true

    # Seed the vault-root .aspignore BEFORE the first capture, so heavy /
    # sensitive machine-local files never enter the (GC-less) event log.
    # Written only when absent — after that it's a normal synced vault file
    # the operator can edit from any device. (.asp/.git/.context/.obsidian/
    # .trash are always excluded by asp itself.)
    if [ ! -f /data/vault/.aspignore ]; then
        cat > /data/vault/.aspignore <<'EOF'
# Agent home (agents/hermes = HERMES_HOME): sync context, not machine state.

# Live SQLite databases — not file-sync-safe while open (state.db, kanban.db).
/agents/hermes/*.db
/agents/hermes/*.db-shm
/agents/hermes/*.db-wal

# Runtime / lock / pid state (machine-local).
/agents/hermes/*.lock
/agents/hermes/**/*.lock
/agents/hermes/*.pid
/agents/hermes/processes.json
/agents/hermes/gateway_state.json
/agents/hermes/channel_directory.json
/agents/hermes/.restart_last_processed.json
/agents/hermes/.update_check
/agents/hermes/.skills_prompt_snapshot.json
/agents/hermes/.profile
/agents/hermes/pairing/
/agents/hermes/sandboxes/

# Logs and caches.
/agents/hermes/*.log
/agents/hermes/logs/
/agents/hermes/cache/
/agents/hermes/.cache/
/agents/hermes/audio_cache/
/agents/hermes/image_cache/
/agents/hermes/models_dev_cache.json

# Toolchains / package managers / binaries (OS-level, machine-local).
/agents/hermes/.bun/
/agents/hermes/.cargo/
/agents/hermes/.rustup/
/agents/hermes/.npm/
/agents/hermes/.local/
/agents/hermes/lsp/
/agents/hermes/bin/

# Secrets and device-bound identity — never sync. platforms/ holds the
# Matrix E2EE crypto store: replicating it to another machine breaks
# encryption (and leaks keys).
/agents/hermes/.env
/agents/hermes/.env.bak
/agents/hermes/auth.json
/agents/hermes/.ssh/
/agents/hermes/platforms/

# Session transcripts churn on every agent turn and there's no log GC yet;
# delete this line to opt in to cross-device session sync.
/agents/hermes/sessions/
EOF
        chown hermes:hermes /data/vault/.aspignore 2>/dev/null || true
    fi

    # Supervised respawn loop (same pattern as the gateway above). `asp watch`
    # reconnects with backoff on its own; the loop covers crashes. ORDERING
    # MATTERS: `watch` must never run before one `clone` has succeeded —
    # watch's startup rescan on a never-synced vault would mint a NEW vault
    # identity that the hub then permanently rejects ("different vault"). The
    # /data/asp/.cloned marker (written only after clone exits 0) gates the
    # switch; a pristine clone instead ADOPTS the hub's vault identity during
    # the handshake, and the first watch rescan after it captures + pushes
    # local files (the migrated agent home included).
    (
      while true; do
        if [ -f /data/asp/.cloned ]; then
          HOME="$HERMES_HOME" ASP_HOME=/data/asp ASP_AUTH_KEY="$ASP_AUTH_KEY" \
            /command/s6-setuidgid hermes asp watch --dir /data/vault --peer "$ASP_REMOTE" \
            >>/data/asp/asp.log 2>&1 || true   # || true: don't let set -e kill the loop
          echo "[init] asp watch exited; respawning in 5s..." >>/data/asp/asp.log
        elif HOME="$HERMES_HOME" ASP_HOME=/data/asp ASP_AUTH_KEY="$ASP_AUTH_KEY" \
            /command/s6-setuidgid hermes asp clone "$ASP_REMOTE" /data/vault \
            >>/data/asp/asp.log 2>&1; then
          touch /data/asp/.cloned
          echo "[init] asp clone ok — switching to watch" >>/data/asp/asp.log
          continue
        else
          echo "[init] asp clone failed (code $?); retrying in 5s..." >>/data/asp/asp.log
        fi
        sleep 5
      done
    ) &
fi

# --- hydroxide: self-hosted ProtonMail bridge (optional, hermes user, bg) -----
# Exposes ProtonMail over local IMAP(1143)/SMTP(1025)/CardDAV(8080)/CalDAV(8081)
# so the agent can reach Proton mail / contacts / calendar via localhost.
#
# Auth is non-interactive. `hydroxide auth` (Proton password + 2FA) is run ONCE
# locally; its encrypted credential file is shipped as the HYDROXIDE_AUTH_B64
# secret (base64 of ~/.config/hydroxide/auth.json). The file holds a rotating
# refresh token — no 2FA at boot. We seed it onto the volume on the FIRST boot
# only; hydroxide then refreshes the token in place at XDG_CONFIG_HOME, so
# re-seeding from a now-stale secret can never clobber a fresher token.
# Servers bind 127.0.0.1 only — never exposed off-box (matches the tailnet-only
# posture; nothing here adds public ingress).
#   HYDROXIDE_AUTH_B64 = base64 of a working auth.json. REQUIRED; unset ⇒ skip.
if [ -z "${HYDROXIDE_AUTH_B64:-}" ]; then
    echo "[init] HYDROXIDE_AUTH_B64 unset — ProtonMail bridge not started" >&2
else
    echo "[init] starting hydroxide ProtonMail bridge (hermes user, supervised)..." >&2
    # XDG_CONFIG_HOME=/data => hydroxide reads/writes /data/hydroxide/auth.json
    # (os.UserConfigDir) and keeps its message cache db there too — all on the
    # persistent volume.
    mkdir -p /data/hydroxide
    if [ ! -f /data/hydroxide/auth.json ]; then
        echo "$HYDROXIDE_AUTH_B64" | base64 -d > /data/hydroxide/auth.json
        echo "[init] seeded hydroxide auth.json onto volume (first boot)" >&2
    fi
    chown -R hermes:hermes /data/hydroxide 2>/dev/null || true
    # Supervised respawn loop (same pattern as the gateway / CSP blocks above):
    # hydroxide is a plain background process here, so this restarts it (5s
    # backoff) if it ever exits.
    (
      while true; do
        HOME=/data/hydroxide XDG_CONFIG_HOME=/data \
          /command/s6-setuidgid hermes hydroxide serve \
          >>/data/hydroxide/hydroxide.log 2>&1
        echo "[init] hydroxide exited (code $?); respawning in 5s..." >>/data/hydroxide/hydroxide.log
        sleep 5
      done
    ) &
fi

# --- bridge (runs as the hermes user, foreground = keeps container alive) -----
# Wait for the cert so the bridge can serve WSS; fall back to plain ws if absent.
echo "[init] waiting for TLS cert..." >&2
i=0
while { [ ! -s /run/tls/tls.crt ] || [ ! -s /run/tls/tls.key ]; } && [ "$i" -lt 180 ]; do
    i=$((i+1)); sleep 1
done

export HOME="$HERMES_HOME" BRIDGE_PORT=$PORT WS_HOST=127.0.0.1
if [ -s /run/tls/tls.crt ] && [ -s /run/tls/tls.key ]; then
    export TLS_CERT=/run/tls/tls.crt TLS_KEY=/run/tls/tls.key
    echo "[init] starting bridge (WSS) on 127.0.0.1:$PORT" >&2
else
    echo "[init] no cert — starting bridge (plain ws) on 127.0.0.1:$PORT" >&2
fi

exec /command/s6-setuidgid hermes node /opt/bridge/bridge.js
