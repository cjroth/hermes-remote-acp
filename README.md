# Hermes ACP over WebSocket (Tailscale-only)

Runs the [Hermes agent](https://github.com/NousResearch/hermes-agent) in a
container and exposes it over the
[Agent Client Protocol (ACP)](https://agentclientprotocol.com) via WebSocket,
reachable **only over your [Tailscale](https://tailscale.com) tailnet** — no
public ingress, no app-level auth to manage.

Hermes speaks ACP over **stdio** out of the box. This project wraps it with
[`stdio-to-ws`](https://github.com/marimo-team/stdio-to-ws) to bridge that
stdio JSON-RPC to a **WebSocket**, then uses **Tailscale Serve** to publish that
socket to your tailnet (and nothing else).

```
ACP client ──ws(s)──► tailscale serve ──► stdio-to-ws ──stdio──► hermes-acp ──► OpenRouter
   (on your tailnet)      (tailnet-only)     (127.0.0.1)
```

Model: `anthropic/claude-sonnet-4-6` (via OpenRouter) — change it in
`hermes_config.yaml`.

## Recommended client: Thunderbolt

[**Thunderbolt**](https://github.com/thunderbird/thunderbolt) (by Mozilla
Thunderbird) is an open-source ACP client for web, desktop, iOS, and Android.
With the device on the same tailnet:

1. **Settings → Agents → Add Custom Agent**
2. **Name:** `Hermes`
3. **URL:** `wss://<node>.<your-tailnet>.ts.net/` (or `ws://…` — see below)
4. Save and start chatting.

> iOS requires `wss://`. The container serves `wss://` automatically once your
> tailnet can provision HTTPS certificates (admin console → **HTTPS
> Certificates**); until then it falls back to `ws://`, which desktop clients
> accept. Either way the connection rides the WireGuard-encrypted tailnet.

## How it works

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds on `nousresearch/hermes-agent` (ships Node.js + `hermes-acp`); adds `stdio-to-ws` and the Tailscale binaries |
| `bridge.sh` | Starts the bridge bound to **loopback only** (`WS_HOST=127.0.0.1`) so nothing but Tailscale Serve can reach it |
| `hermes_config.yaml` | OpenRouter provider + model |
| `s6/tailscaled/` | Runs `tailscaled` in userspace mode (no TUN / no `NET_ADMIN` needed) |
| `s6/tailscale-up/` | Joins the tailnet and runs `tailscale serve` (HTTPS→`wss` with `ws` fallback) |

The bridge listens on `127.0.0.1` only. `tailscale serve` reaches it over
loopback; anything from outside the container (a host's public proxy, the
internet) cannot — that is the access boundary.

## Configuration

Set as container environment variables / secrets:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | yes | Inference via OpenRouter |
| `TS_AUTHKEY` | yes | Tailscale auth key — **non-ephemeral, reusable** (ephemeral nodes can't hold TLS certs, so `wss://` needs non-ephemeral) |
| `TS_HOSTNAME` | no | Tailnet node name (default `hermes-acp`) |
| `PORT` | no | Bridge port (default `3000`; most PaaS hosts inject this) |

**Persistent volume:** mount one at `/var/lib/tailscale`. It keeps the node's
identity stable across restarts/redeploys and stores the TLS cert (which
requires an on-disk state dir — in-memory state can't provision certs).

## Build & run

```bash
docker build -t hermes-acp .
docker run -d \
  -e OPENROUTER_API_KEY=sk-or-... \
  -e TS_AUTHKEY=tskey-auth-... \
  -e TS_HOSTNAME=hermes-acp \
  -v hermes-ts-state:/var/lib/tailscale \
  hermes-acp
```

Then connect an ACP client to `ws(s)://<node>.<your-tailnet>.ts.net/`.

## Notes

- Use `marimo-team/stdio-to-ws`, **not** `@rebornix/stdio-to-ws` — the latter
  doesn't newline-terminate stdin writes, which hermes-acp's `readline()` parser
  needs. (The Dockerfile also patches `stdio-to-ws` to honor `WS_HOST`, since its
  CLI has no host-bind flag.)
- ACP specifics: protocol version is the integer `1`; prompts use
  `session/prompt` with `prompt: [{ type: "text", text: "…" }]`; replies stream
  as `session/update` notifications (`update.sessionUpdate = "agent_message_chunk"`).
- `wss://` depends on your tailnet's HTTPS-certificate provisioning. If
  `tailscale cert` fails (e.g. a control-plane `SetDNS` error), the container
  serves `ws://` and upgrades to `wss://` automatically on the next restart once
  certs succeed.
