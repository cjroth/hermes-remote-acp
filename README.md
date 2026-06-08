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
| **Self-update** | the `self-update` skill + a `/data/repo` clone — the agent edits its own skills and pushes them to GitHub | `GITHUB_TOKEN` |
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

## Fork it & let it improve its own skills

c-stack can edit its **own skills** while running and push the changes back to
your fork, so the agent's improvements persist instead of being lost on the next
reboot. To enable this on your own deployment:

1. **Fork this repo** to your GitHub account (`youruser/c-stack`). Your fork is
   where the agent commits its skill edits.

2. **Create a fine-grained Personal Access Token** scoped to *just that fork*:
   GitHub → *Settings → Developer settings → Fine-grained tokens → Generate new
   token* → **Repository access: Only select repositories → `youruser/c-stack`**
   → **Permissions → Repository → Contents: Read and write**. Nothing else is
   needed. (The token is repo-scoped, not path-scoped — it *can* technically
   touch any file in the repo, but the `self-update` skill only ever stages
   changes under `skills/`.)

3. **Give it to the deployment** as Fly secrets:

   ```sh
   fly secrets set GITHUB_TOKEN=github_pat_xxxxxxxx
   fly secrets set GITHUB_REPO=youruser/c-stack   # required for forks
   ```

4. **Deploy.** On boot, `init.sh` clones your fork to `/data/repo` (on the
   persistent volume) and refreshes the live skills from it.

After that, the flow is: the agent edits a skill under `/data/repo/skills/<name>`,
runs the `self-update` skill to commit + push to `main`, and the change is live
immediately on that machine. Every other machine picks it up on its next boot —
`fly deploy` or `fly apps restart`, **no image rebuild required**. Pushes go
straight to `main`; your review happens at deploy time, since a push alone
doesn't restart anything.

See [DEPLOYMENT.md → Self-update](DEPLOYMENT.md#self-update-let-the-agent-improve-its-own-skills)
for the full mechanism, token handling, and limits.
