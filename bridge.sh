#!/bin/sh
set -e

# The bridge terminates TLS itself (see bridge.js header for why) using the
# Tailscale-provisioned cert that the `tailscale-up` service writes to
# /run/tls/. It binds loopback only; `tailscale serve --tcp=443` forwards the
# tailnet to it. Wait for the cert to appear, then serve WSS.
CERT=/run/tls/tls.crt
KEY=/run/tls/tls.key
export BRIDGE_PORT=8443
export WS_HOST=127.0.0.1

echo "[bridge] waiting for TLS cert from tailscale-up..." >&2
i=0
while [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; do
    i=$((i + 1))
    if [ "$i" -gt 180 ]; then
        echo "[bridge] no cert after 180s — starting plaintext ws:// (wss won't work)" >&2
        break
    fi
    sleep 1
done

if [ -s "$CERT" ] && [ -s "$KEY" ]; then
    export TLS_CERT="$CERT" TLS_KEY="$KEY"
    echo "[bridge] cert found — serving WSS on ${WS_HOST}:${BRIDGE_PORT}" >&2
fi

exec node /opt/bridge/bridge.js
