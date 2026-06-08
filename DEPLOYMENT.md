# Deploying c-stack

How c-stack is built and deployed. For a guided, step-by-step setup run the
`setup` skill (`/setup` in Claude Code) — it walks you through everything below
and lets you skip the integrations you don't want.

## Architecture

Hermes speaks ACP over **stdio**. A small custom bridge (`bridge.js`) turns that
into a **WebSocket** and terminates TLS, while **Tailscale Serve** forwards raw
TCP from the tailnet to it (and nothing else). It's reachable **only over your
[Tailscale](https://tailscale.com) tailnet** — no public ingress, no app-level
auth to manage.

```
ACP client ──wss──► tailscale serve --tcp ──► bridge.js ──stdio──► hermes-acp ──► OpenRouter
  (on your tailnet)   (tailnet-only, raw TCP)   (TLS, 127.0.0.1)
```

Model: `deepseek/deepseek-v4-flash` (via OpenRouter) — change it in
`hermes_config.yaml`.

The bridge listens on `127.0.0.1` only, so only `tailscale serve` (running in the
same container) can reach it — that's the access boundary.

## Host requirement: a TUN-capable host

It needs a host that gives the container a real **kernel TUN device**
(`/dev/net/tun` + `NET_ADMIN`) — e.g. a **[Fly.io](https://fly.io) VM** (see
`fly.toml`) or a VPS — and won't start otherwise.

On hosts that forbid TUN (many PaaS platforms), Tailscale falls back to
**userspace networking**, whose software net stack stalls the TLS handshake
(5–30s connects that wedge after a couple). Kernel TUN keeps connects ~1s and
stable. The bridge also terminates TLS itself (rather than `tailscale serve
--https`) because serve's TLS path is the part that stalls in userspace; raw
`serve --tcp` passthrough is fast and stable.

## How it works

| File | Purpose |
|------|---------|
| `init.sh` | Entrypoint. Starts `tailscaled` (kernel TUN), joins the tailnet, provisions the TLS cert, runs `tailscale serve --tcp=443`, then launches the bridge as the `hermes` user. Replaces the base image's s6 init (which needs PID 1, unavailable on Fly). |
| `bridge.js` | stdio⇄WebSocket bridge. Terminates TLS with the tailnet cert, binds `127.0.0.1` only, newline-frames stdin for hermes-acp's `readline()` parser. |
| `hermes_config.yaml` | OpenRouter provider + model, plus Matrix streaming config. |
| `skills/proton/` | The `proton` skill — teaches the agent to drive the hydroxide bridge (mail/calendar/contacts) via a stdlib-only helper script. Bundled into the image and refreshed into `/data` on every boot. |
| `Dockerfile` | Builds on `nousresearch/hermes-agent`; adds `ws`, the Tailscale binaries, hydroxide (Proton bridge), the `ctx` CSP CLI, the `ntn` Notion CLI, the Matrix E2EE deps (`mautrix[encryption]`), the `proton` skill, and the entrypoint. |
| `fly.toml` | Fly.io deploy: a region near you, a volume for Tailscale state, **no public services** (tailnet-only). |
| `beeper_login.py` | One-off helper that mints a Matrix access token for a Beeper account (Beeper's email-code → JWT flow). Used to set up the Matrix/Beeper gateway. |

## Configuration

Container environment variables / secrets:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | yes | Inference via OpenRouter |
| `TS_AUTHKEY` | yes | Tailscale auth key — **non-ephemeral, reusable** (ephemeral nodes can't hold TLS certs) |
| `TS_HOSTNAME` | no | Tailnet node name (default `hermes`) |
| `MATRIX_HOMESERVER` | no | Matrix homeserver URL. For Beeper: `https://matrix.beeper.com`. Enables the Matrix gateway (see [Talk to it from Beeper](#talk-to-it-from-beeper-matrix)). |
| `MATRIX_ACCESS_TOKEN` | no | Matrix access token for the bot account (mint it with `beeper_login.py`). Presence of this auto-starts the gateway. |
| `MATRIX_DEVICE_ID` | no | Stable device ID paired with the token — keep it constant so the bot's E2EE identity survives restarts. |
| `MATRIX_ENCRYPTION` | no | `true` to enable E2EE (**required for Beeper** — its rooms are encrypted). |
| `MATRIX_RECOVERY_KEY` | no | The bot account's Beeper recovery key — lets it cross-sign its own device so other clients share encryption sessions with it. |
| `MATRIX_ALLOWED_USERS` | no | Comma-separated Matrix user IDs allowed to talk to the bot (e.g. your main `@you:beeper.com`). Lock this down. |
| `HYDROXIDE_AUTH_B64` | no | base64 of a working hydroxide `auth.json` (mint it once locally with `hydroxide auth`). Presence auto-starts the ProtonMail bridge (IMAP/SMTP/CalDAV/CardDAV on localhost). |
| `USER_PRIMARY_EMAIL` | no | The operator's own email address — used as "the user's email" for calendar/email invites and as the default recipient for the `email-me` / `lesswrong-digest` skills. Skills that need it report when it's unset rather than guessing. |
| `NOTION_API_KEY` | no | Notion integration token — aliased to `NOTION_API_TOKEN` so the `ntn` CLI and the `notion` skill light up. |
| `CTX_AUTH_KEY` | no | [CSP](https://github.com/cjroth/csp) §10 enrollment secret — an opaque pre-shared bearer key (no fixed format) that enrolls this container into a remote vault and syncs `/data/vault`. Unset ⇒ vault sync is skipped with a logged warning. |
| `CSP_REMOTE` | no | CSP remote vault URL (`wss://host[:port]`, or `ws://…` if plaintext) to clone/watch. Required alongside `CTX_AUTH_KEY` for sync to start. |
| `GITHUB_TOKEN` | no | Fine-grained GitHub PAT (Contents: read/write on the source repo). Presence enables **self-update**: init.sh clones the repo to `/data/repo` and the `self-update` skill can push skill edits back to `main`. See [Self-update](#self-update-let-the-agent-improve-its-own-skills). |
| `GITHUB_REPO` | no | `owner/repo` to clone for self-update (default `cjroth/c-stack`). **Forks must set this** to their own `owner/c-stack`. |
| `GIT_USER_NAME` | no | Commit author name for self-update pushes (default `hermes-agent`). |
| `GIT_USER_EMAIL` | no | Commit author email (default `USER_PRIMARY_EMAIL`, else `hermes@localhost`). |

**Persistent volume at `/var/lib/tailscale`:** keeps the node identity + TLS cert
across restarts (an on-disk state dir is required for certs).

## Self-update: let the agent improve its own skills

With `GITHUB_TOKEN` set, the agent can edit its **own skills** and push the
changes back to GitHub, so improvements persist instead of being lost on the
next reboot.

**Why it's needed:** the live skills dir (`/data/hermes/skills/...`) is
regenerated on every boot, so an in-place edit there is wiped on restart. The
only durable path is pushing back to the source repo.

**How it works:**

- `init.sh` clones the repo (`GITHUB_REPO`) to `/data/repo` on the persistent
  volume, and `git fetch`/`reset --hard origin/main` on every boot.
- The skill refresh then sources skills from `/data/repo` (falling back to the
  image when the clone is absent). So a skill change pushed to `main` goes live
  on **any** machine's next boot — `fly deploy` or `fly apps restart`, **no
  image rebuild required**.
- The `self-update` skill drives the loop: edit under `/data/repo/skills/<name>`,
  then `scripts/push-skill.sh "<message>" <name>` commits + pushes to `main` and
  refreshes the live copy so it's active in the current session.

**Pushes go straight to `main`** (no review gate before the push); the human
review happens at deploy time, since a push alone doesn't restart anything. The
helper stages **only paths under `skills/`**, so the agent can't commit
`Dockerfile`/`init.sh`/other core files through it — even though a repo-scoped
token technically could. Token handling: the PAT is never written to
`/data/repo/.git/config`; pushes read it from the env via a git credential
helper.

**Token scope:** create a *fine-grained* PAT limited to the single repo with
**Contents: read and write** (add **Pull requests: read and write** only if you
later switch to a PR-based flow). Set it as a Fly secret:

```sh
fly secrets set GITHUB_TOKEN=github_pat_xxx
# forks also:
fly secrets set GITHUB_REPO=youruser/c-stack
```

## Connecting a client: Thunderbolt

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

## Talk to it from Beeper (Matrix)

[Beeper](https://www.beeper.com) is a hosted **Matrix** homeserver
(`matrix.beeper.com`), so Hermes reaches it through its built-in **Matrix
gateway** — no new protocol code. The gateway runs as a supervised background
process *alongside* the ACP bridge (see `init.sh`), so **ACP and Beeper work at
the same time** on the same machine; neither replaces the other.

> Beeper has no password login — auth goes through Beeper's email-code → JWT
> flow. Hermes authenticates with an **access token** (it calls `/whoami`), so
> once you mint a token the stock Matrix adapter works against Beeper unchanged.

### 1. Make a dedicated bot account

Sign up a **second Beeper account** with its own email — that's the bot. (Don't
log the bot in as your main account, or it would see and could reply inside
*every* bridged chat in your inbox.) From your **main** Beeper account, start a
chat with the bot account so there's a room to talk in.

### 2. Mint a Matrix access token

Run the helper locally (stdlib-only, no installs) for the **bot** account:

```bash
python3 beeper_login.py --app hermes-acp-nrt
# enter the bot's email, then the 6-digit code Beeper emails it
```

It prints `MATRIX_ACCESS_TOKEN`, `MATRIX_USER_ID`, `MATRIX_DEVICE_ID` and a
ready-to-paste `fly secrets set` line. Keep the token + device ID together — the
device ID is tied to the bot's E2EE identity.

### 3. Set the secrets

```bash
fly secrets set -a hermes-acp-nrt \
  MATRIX_HOMESERVER=https://matrix.beeper.com \
  MATRIX_ACCESS_TOKEN=syt_... \
  MATRIX_DEVICE_ID=ABCDEF... \
  MATRIX_ENCRYPTION=true \
  MATRIX_RECOVERY_KEY="EsT... bot account's Beeper recovery key" \
  MATRIX_ALLOWED_USERS=@your-main-user:beeper.com
```

`MATRIX_ENCRYPTION=true` is **required** — Beeper rooms are end-to-end
encrypted. Get `MATRIX_RECOVERY_KEY` from the bot account's **Beeper → Settings →
Encryption** (it lets the bot cross-sign its device so your client shares
encryption sessions with it). The crypto store persists on the volume at
`/data/hermes/platforms/matrix/store`.

### 4. Deploy and chat

```bash
fly deploy -a hermes-acp-nrt --ha=false
```

The gateway connects within a few seconds (`fly logs` shows
`starting messaging gateway (...): matrix`). Message the bot from your main
account — a DM gets a response to every message (no `@mention` needed).

> **Note on DMs:** a direct chat with the bot is a 2-member room, which Hermes
> treats as a DM (responds to everything) — exactly what you want for a personal
> assistant. The known upstream quirk where 2-member *group* rooms are
> misclassified ([hermes-agent#24114](https://github.com/NousResearch/hermes-agent/issues/24114))
> doesn't affect this direct-DM flow.

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
- **CSP vault sync** (`CTX_AUTH_KEY` + `CSP_REMOTE`): the `ctx` binary clones the
  remote vault into `/data/vault` on first boot, then `watch`es it (the synced
  folder lives on the persistent volume, so it survives restarts and isn't
  re-cloned). `CTX_AUTH_KEY` is CSP's §10 pre-shared enrollment secret: `ctx`
  sends it as a bearer token on connect, the remote authorizes this node's
  auto-generated key (persisted at `/data/csp/id_ed25519`), and after first
  enrollment the node's key is durable in the remote's `authorized_keys`. Logs
  go to `/data/csp/csp.log` inside the container.
