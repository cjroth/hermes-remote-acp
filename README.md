# Hermes ACP over WebSocket (Tailscale-only)

Runs the [Hermes agent](https://github.com/NousResearch/hermes-agent) in a
container and exposes it over the
[Agent Client Protocol (ACP)](https://agentclientprotocol.com) via WebSocket,
reachable **only over your [Tailscale](https://tailscale.com) tailnet** — no
public ingress, no app-level auth to manage.

Hermes speaks ACP over **stdio**. A small custom bridge (`bridge.js`) turns that
into a **WebSocket** and terminates TLS, while **Tailscale Serve** forwards raw
TCP from the tailnet to it (and nothing else).

```
ACP client ──wss──► tailscale serve --tcp ──► bridge.js ──stdio──► hermes-acp ──► OpenRouter
  (on your tailnet)   (tailnet-only, raw TCP)   (TLS, 127.0.0.1)
```

Model: `anthropic/claude-sonnet-4-6` (via OpenRouter) — change it in
`hermes_config.yaml`.

## ⚠️ Run it on a TUN-capable host

This needs a host that gives the container a real **kernel TUN device**
(`/dev/net/tun` + `NET_ADMIN`) — e.g. a **[Fly.io](https://fly.io) VM** (see
`fly.toml`) or a VPS. It deliberately refuses to start otherwise.

Why: on hosts that forbid TUN (many PaaS platforms), Tailscale falls back to
**userspace networking**, whose software net stack *stalls the TLS handshake* —
connections take 5–30s and wedge after a couple. Kernel TUN handles inbound in
the kernel, so connections are ~1s and stable. The bridge also terminates TLS
itself (rather than `tailscale serve --https`) because serve's TLS path is the
part that stalls in userspace; raw `serve --tcp` passthrough is fast and stable.

## Recommended client: Thunderbolt

[**Thunderbolt**](https://github.com/thunderbird/thunderbolt) (by Mozilla
Thunderbird) is an open-source ACP client for web, desktop, iOS, and Android.
With the device on the same tailnet:

1. **Settings → Agents → Add Custom Agent**
2. **Name:** `Hermes`
3. **URL:** `wss://<node>.<your-tailnet>.ts.net/`  (must match the node's name —
   that's what the TLS cert is issued for)
4. Save and start chatting.

> iOS requires `wss://`, which needs **HTTPS Certificates** enabled on your
> tailnet (admin console → DNS). Tip: put the node near you — a distant region
> adds latency to every handshake.

## How it works

| File | Purpose |
|------|---------|
| `init.sh` | Entrypoint. Starts `tailscaled` (kernel TUN), joins the tailnet, provisions the TLS cert, runs `tailscale serve --tcp=443`, then launches the bridge as the `hermes` user. Replaces the base image's s6 init (which needs PID 1, unavailable on Fly). |
| `bridge.js` | stdio⇄WebSocket bridge. Terminates TLS with the tailnet cert, binds `127.0.0.1` only, newline-frames stdin for hermes-acp's `readline()` parser. |
| `hermes_config.yaml` | OpenRouter provider + model. |
| `Dockerfile` | Builds on `nousresearch/hermes-agent` (ships Node.js + `hermes-acp`); adds `ws`, the Tailscale binaries, and the entrypoint. |
| `fly.toml` | Fly.io deploy: a region near you, a volume for Tailscale state, **no public services** (tailnet-only). |

The bridge listens on `127.0.0.1` only, so only `tailscale serve` (running in the
same container) can reach it — that's the access boundary.

## Configuration

Container environment variables / secrets:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | yes | Inference via OpenRouter |
| `TS_AUTHKEY` | yes | Tailscale auth key — **non-ephemeral, reusable** (ephemeral nodes can't hold TLS certs) |
| `TS_HOSTNAME` | no | Tailnet node name (default `hermes`) |

**Persistent volume at `/var/lib/tailscale`:** keeps the node identity + TLS cert
across restarts (an on-disk state dir is required for certs).

## Deploy (Fly.io)

```bash
fly apps create <app>
fly secrets set -a <app> OPENROUTER_API_KEY=sk-or-... TS_AUTHKEY=tskey-auth-...
fly volumes create ts_state --region <nearest> --size 1 -a <app>
fly deploy -a <app> --ha=false
```

Then connect an ACP client to `wss://<node>.<your-tailnet>.ts.net/`.

## Notes

- ACP specifics: protocol version is the integer `1`; prompts use
  `session/prompt` with `prompt: [{ type: "text", text: "…" }]`; replies stream
  as `session/update` notifications (`update.sessionUpdate = "agent_message_chunk"`).
- The cert is provisioned at boot via `tailscale cert` and cached in the volume.
  Manual certs don't auto-renew the way `serve --https` does, so a periodic
  restart (well within the ~90-day cert life) re-provisions it.
