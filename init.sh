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

mkdir -p /var/run/tailscale /var/lib/tailscale /dev/net /run/tls

# /opt/data (HERMES_HOME) is a persistent volume — Hermes keeps sessions, memory,
# state.db and learned skills here across restarts. Fly mounts it root-owned, so
# hand it to the hermes user, then (re)seed config.yaml from the image (repo is
# the source of truth for the model/provider; runtime data persists alongside).
chown hermes:hermes /opt/data 2>/dev/null || true
install -o hermes -g hermes -m 644 /opt/seed/config.yaml /opt/data/config.yaml 2>/dev/null || \
    cp /opt/seed/config.yaml /opt/data/config.yaml

# --- tailscaled: requires a real kernel TUN device ---------------------------
# We deliberately do NOT fall back to userspace networking: its software net
# stack stalls TLS handshakes (5-30s connects that wedge after a couple). So we
# require kernel TUN and fail loudly if the host forbids it (e.g. Railway). Run
# on a TUN-capable host (Fly.io VMs, a VPS, etc.).
[ -c /dev/net/tun ] || mknod /dev/net/tun c 10 200 2>/dev/null || true
if [ ! -c /dev/net/tun ]; then
    echo "[init] FATAL: no /dev/net/tun. This needs a TUN-capable host (Fly.io VM, VPS, …)." >&2
    echo "[init] Userspace-networking Tailscale stalls TLS handshakes; refusing to run in it." >&2
    exit 1
fi
echo "[init] kernel TUN mode" >&2
/usr/local/bin/tailscaled --statedir=/var/lib/tailscale --socket="$SOCK" >/tmp/tailscaled.log 2>&1 &

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

# --- bridge (runs as the hermes user, foreground = keeps container alive) -----
# Wait for the cert so the bridge can serve WSS; fall back to plain ws if absent.
echo "[init] waiting for TLS cert..." >&2
i=0
while { [ ! -s /run/tls/tls.crt ] || [ ! -s /run/tls/tls.key ]; } && [ "$i" -lt 180 ]; do
    i=$((i+1)); sleep 1
done

export HOME=/opt/data BRIDGE_PORT=$PORT WS_HOST=127.0.0.1
if [ -s /run/tls/tls.crt ] && [ -s /run/tls/tls.key ]; then
    export TLS_CERT=/run/tls/tls.crt TLS_KEY=/run/tls/tls.key
    echo "[init] starting bridge (WSS) on 127.0.0.1:$PORT" >&2
else
    echo "[init] no cert — starting bridge (plain ws) on 127.0.0.1:$PORT" >&2
fi

exec /command/s6-setuidgid hermes node /opt/bridge/bridge.js
