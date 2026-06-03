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

mkdir -p /var/run/tailscale /data/hermes /data/tailscale /dev/net /run/tls

# One persistent volume at /data holds everything that must survive restarts:
#   /data/hermes    = HERMES_HOME (sessions, memory, state.db, learned skills)
#   /data/tailscale = tailscaled state (node identity + TLS cert)
# Fly mounts /data root-owned, so hand the hermes home to the hermes user, then
# (re)seed config.yaml from the image (repo is the source of truth for the
# model/provider; runtime data persists alongside it).
chown hermes:hermes /data/hermes 2>/dev/null || true
install -o hermes -g hermes -m 644 /opt/seed/config.yaml /data/hermes/config.yaml 2>/dev/null || \
    cp /opt/seed/config.yaml /data/hermes/config.yaml

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

# --- Telegram gateway (optional, runs as hermes user, background) ------------
# Outbound-only (long-polls Telegram's API), so it's unaffected by the
# tailnet-only lockdown. Setting TELEGRAM_BOT_TOKEN auto-enables the platform
# (gateway _apply_env_overrides), so no interactive `gateway setup` is needed.
# State (telegram offset, sessions) lives in HERMES_HOME=/data/hermes (volume).
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "[init] starting Telegram gateway (hermes user, supervised)..." >&2
    # Supervised respawn loop: the gateway is a plain background process (no s6 /
    # systemd here), so if it ever exits — crash, OOM, or the agent stopping it —
    # nothing would restart it and it'd stay dead until the next machine reboot.
    # This loop respawns it (5s backoff) so the bot self-heals. Each respawn is
    # logged. A clean config won't loop; a bad one logs every 5s (visible).
    (
      while true; do
        HOME=/data/hermes HERMES_HOME=/data/hermes \
          /command/s6-setuidgid hermes /opt/hermes/.venv/bin/hermes gateway run \
          >>/data/hermes/gateway.log 2>&1
        echo "[init] Telegram gateway exited (code $?); respawning in 5s..." >>/data/hermes/gateway.log
        sleep 5
      done
    ) &
else
    echo "[init] TELEGRAM_BOT_TOKEN unset — Telegram gateway not started" >&2
fi

# --- CSP context vault sync (optional, runs as hermes user, background) -------
# Keeps /data/vault (on the persistent volume) synced with a remote CSP vault
# via the `ctx` CLI: clone it on the first boot, then `watch` (reconnecting to
# the saved origin) on every boot after.
#
# Auth is CSP's §10 enrollment model: CTX_AUTH_KEY is a pre-shared, opaque
# bearer secret (no fixed format) that `ctx` sends on the WS upgrade. A remote
# requiring enrollment accepts it and durably authorizes THIS node's own
# public key, so the device just generates its own identity — persisted at
# /data/csp/id_ed25519 (on the volume) so it stays stable across restarts and
# doesn't churn fresh enrollments. The reverse trust (this node trusting the
# server) is bootstrapped by `clone` via trust-on-first-use.
#   CTX_AUTH_KEY = pre-shared enrollment secret. REQUIRED (read directly by
#                  `ctx`); unset ⇒ vault sync is skipped with a warning.
#   CSP_REMOTE   = remote vault URL (wss://host[:port], or ws://… if plaintext).
if [ -z "${CTX_AUTH_KEY:-}" ]; then
    echo "[init] CTX_AUTH_KEY unset — no auth key set; CSP vault sync not started" >&2
elif [ -z "${CSP_REMOTE:-}" ]; then
    echo "[init] CSP_REMOTE unset — no remote to connect to; CSP vault sync not started" >&2
else
    echo "[init] starting CSP vault sync (hermes user, supervised) → $CSP_REMOTE" >&2
    mkdir -p /data/csp /data/vault
    chown -R hermes:hermes /data/csp /data/vault 2>/dev/null || true
    # Supervised respawn loop (same pattern as the gateway above): ctx runs as
    # a plain background process here, so this restarts it (5s backoff) if it
    # ever exits. The clone-vs-watch choice is re-evaluated each iteration, so
    # once /data/vault exists, respawns take the watch path (clone refuses to
    # clobber an existing vault). ctx auto-generates the identity at
    # CTX_IDENTITY on first run; CTX_AUTH_KEY is inherited from the env.
    (
      while true; do
        if [ -d /data/vault/.context ]; then
          HOME=/data/hermes CTX_IDENTITY=/data/csp/id_ed25519 CTX_AUTH_KEY="$CTX_AUTH_KEY" \
            /command/s6-setuidgid hermes ctx --dir /data/vault watch \
            >>/data/csp/csp.log 2>&1
        else
          HOME=/data/hermes CTX_IDENTITY=/data/csp/id_ed25519 CTX_AUTH_KEY="$CTX_AUTH_KEY" \
            /command/s6-setuidgid hermes ctx clone "$CSP_REMOTE" /data/vault --watch \
            >>/data/csp/csp.log 2>&1
        fi
        echo "[init] CSP vault sync exited (code $?); respawning in 5s..." >>/data/csp/csp.log
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

export HOME=/data/hermes BRIDGE_PORT=$PORT WS_HOST=127.0.0.1
if [ -s /run/tls/tls.crt ] && [ -s /run/tls/tls.key ]; then
    export TLS_CERT=/run/tls/tls.crt TLS_KEY=/run/tls/tls.key
    echo "[init] starting bridge (WSS) on 127.0.0.1:$PORT" >&2
else
    echo "[init] no cert — starting bridge (plain ws) on 127.0.0.1:$PORT" >&2
fi

exec /command/s6-setuidgid hermes node /opt/bridge/bridge.js
