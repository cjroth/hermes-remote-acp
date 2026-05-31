#!/bin/sh
set -e

PORT="${PORT:-3000}"
echo "[bridge] Starting Hermes ACP WebSocket server on port ${PORT}" >&2
echo "[bridge] Connect via ws://host:${PORT}" >&2

# --persist: keep hermes-acp alive across client disconnects
# --grace-period -1: never kill the process (Railway manages the container)
# marimo-team/stdio-to-ws: --framing line (default) appends \n to each stdin write,
# which is required for hermes-acp's readline()-based JSON-RPC parser.
# Each WebSocket connection spawns its own hermes-acp process.
exec stdio-to-ws --port "${PORT}" "hermes-acp"
