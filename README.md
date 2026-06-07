# Chris's Opinionated Hermes Agent Stack (c-stack)

Runs the [Hermes agent](https://github.com/NousResearch/hermes-agent) as a
personal assistant in a container, exposed over the
[Agent Client Protocol (ACP)](https://agentclientprotocol.com) via WebSocket and
reachable **only over your [Tailscale](https://tailscale.com) tailnet** — no
public ingress, no app-level auth to manage. Bundles a few opinionated
integrations (Proton, Beeper, Notion, vault sync), each optional and turned on
only by supplying its secret.

## What's in it

| Capability | What's built in | Turned on by |
|------------|-----------------|--------------|
| **ACP over WebSocket** | `bridge.js` stdio⇄WSS bridge (terminates TLS) | always on |
| **Tailscale** | `tailscaled` + cert provisioning + `serve --tcp` (tailnet-only ingress) | `TS_AUTHKEY` |
| **Proton** (mail · calendar · contacts) | [hydroxide](https://github.com/emersion/hydroxide) bridge on localhost + the `proton` skill | `HYDROXIDE_AUTH_B64` |
| **Matrix / Beeper** chat | Hermes gateway with E2EE (`mautrix[encryption]`), progressive streaming | `MATRIX_ACCESS_TOKEN` |
| **Notion** | official `ntn` CLI + the bundled `notion` skill | `NOTION_API_KEY` |
| **CSP vault sync** | [`ctx`](https://github.com/cjroth/csp) clone-and-watch of `/data/vault` | `CTX_AUTH_KEY` + `CSP_REMOTE` |
| **Fly.io deploy** | `fly.toml` — region, volume, no public services | — |

## Setup & deployment

- **Guided setup:** run the `setup` skill — `/setup` in Claude Code — for a
  step-by-step walkthrough that lets you skip the integrations you don't want.
- **Reference:** see [DEPLOYMENT.md](DEPLOYMENT.md) for the architecture, the
  full configuration/secrets table, the Fly.io deploy commands, the Beeper
  setup, and operational notes.

Recommended client: [**Thunderbolt**](https://github.com/thunderbird/thunderbolt)
(open-source ACP client for web, desktop, iOS, Android) — point it at
`wss://<node>.<your-tailnet>.ts.net/`.
