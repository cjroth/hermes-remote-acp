# Hermes ACP over WebSocket

Runs the [Hermes agent](https://github.com/NousResearch/hermes-agent) on
[Railway](https://railway.com) and exposes it over the
[Agent Client Protocol (ACP)](https://agentclientprotocol.com) via WebSocket,
so any ACP client can talk to it from anywhere.

Hermes speaks ACP over **stdio** out of the box. This project wraps it with
[`stdio-to-ws`](https://github.com/marimo-team/stdio-to-ws) to bridge that
stdio JSON-RPC to a **WebSocket** — no auth yet (that comes later via Tailscale).

```
ACP client  ──wss──►  stdio-to-ws  ──stdio──►  hermes-acp  ──►  OpenRouter
```

## Live endpoint

```
wss://pacific-flow-production-d3fc.up.railway.app
```

Model: `anthropic/claude-sonnet-4-6` (via OpenRouter).

## Recommended client: Thunderbolt

[**Thunderbolt**](https://github.com/thunderbird/thunderbolt) (by Mozilla
Thunderbird) is an open-source ACP client for web, desktop, iOS, and Android.
To connect it to this agent:

1. **Settings → Agents → Add Custom Agent**
2. **Name:** `Hermes`
3. **URL:** `wss://pacific-flow-production-d3fc.up.railway.app`
4. Save and start chatting.

> iOS requires `wss://` (secure) — which this endpoint already uses.

## How it works

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds on `nousresearch/hermes-agent` (ships Node.js + `hermes-acp`), adds the `stdio-to-ws` bridge |
| `bridge.sh` | Starts `stdio-to-ws --port $PORT "hermes-acp"` |
| `hermes_config.yaml` | Sets the OpenRouter provider + model |

Railway injects `PORT` and the `OPENROUTER_API_KEY` env var at runtime.

> **Note:** use `marimo-team/stdio-to-ws`, *not* `@rebornix/stdio-to-ws` — the
> latter doesn't newline-terminate stdin writes, which hermes-acp's
> `readline()` parser needs.

## Deploy your own

```bash
railway init
railway variables --set OPENROUTER_API_KEY=sk-or-...
railway up
railway domain        # get your wss:// URL
```

## Roadmap

- [ ] Tailscale auth (currently open — POC only)
