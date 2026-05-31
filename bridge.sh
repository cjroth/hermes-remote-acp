#!/bin/sh
set -e

PORT="${PORT:-3000}"

# Bind the bridge to loopback ONLY. `tailscale serve` (running in this same
# container) proxies the tailnet to 127.0.0.1:$PORT, so the tailnet path works —
# but Railway's public edge proxy reaches the container over its private network
# interface, NOT loopback, so the public domain can't reach the bridge at all.
# This is the technical enforcement of "tailnet-only": no external ingress even
# if a public domain exists. (stdio-to-ws is patched in the Dockerfile to honor
# WS_HOST.)
export WS_HOST=127.0.0.1

echo "[bridge] Starting Hermes ACP WebSocket server on ${WS_HOST}:${PORT}" >&2

# marimo-team/stdio-to-ws: default --framing line appends \n to each stdin write,
# which hermes-acp's readline()-based JSON-RPC parser requires. Each WebSocket
# connection spawns its own hermes-acp process.
exec stdio-to-ws --port "${PORT}" "hermes-acp"
