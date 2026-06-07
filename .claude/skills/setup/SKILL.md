---
name: setup
description: Walk an operator through deploying c-stack (Chris's Opinionated Hermes Agent Stack) — core Fly.io + Tailscale deploy plus the optional Proton, Matrix/Beeper, Notion, and CSP-vault integrations. Use when the user wants to set up, deploy, install, or configure this stack from scratch, or wire up one of its integrations.
---

# Set up c-stack

Drive the operator through standing up this stack on a TUN-capable host and
wiring whichever integrations they want. Go through the phases **in order**.
Phase 1 (core deploy) is required; **every integration phase after it is
optional — ask before each one and skip cleanly if they decline.**

## How to run this walkthrough

- Work one phase at a time. After each phase, confirm it succeeded before moving on.
- Before an optional phase, ask the user whether they want it (e.g. "Set up
  Proton mail/calendar/contacts? (y/skip)"). If they skip, don't set its
  secrets — the container simply won't start that integration.
- Some steps need an **interactive login** the agent can't do for the user
  (`fly auth login`, `hydroxide auth`, `beeper_login.py`'s email-code prompt).
  For those, tell the user to run the command themselves by typing `! <command>`
  in the prompt so its output lands in the session, then continue.
- Collect the app name once and reuse it. Suggest a Fly app name and store the
  user's choice; substitute it for `<app>` everywhere below.
- Never echo secret values back in full. When setting Fly secrets, run the
  command; don't print the resulting key material.

## Phase 0 — Prerequisites (required)

Confirm before deploying:

1. **A TUN-capable host.** The container needs a real kernel TUN device
   (`/dev/net/tun` + `NET_ADMIN`). A Fly.io VM (this repo's `fly.toml`) or a VPS
   works; most other PaaS platforms force userspace networking, which stalls the
   TLS handshake — don't use those.
2. **`flyctl` installed and authenticated.** Check with `fly version` and
   `fly auth whoami`. If not logged in, have the user run `! fly auth login`.
3. **An OpenRouter API key** (`sk-or-...`) for inference.
4. **A Tailscale account** with a **non-ephemeral, reusable** auth key
   (`tskey-auth-...`). It must be non-ephemeral — ephemeral nodes can't hold TLS
   certs. For iOS clients later, enable **HTTPS Certificates** in the tailnet
   admin console (DNS tab).

## Phase 1 — Core deploy: OpenRouter + Tailscale (required)

This brings up the ACP-over-WebSocket bridge on the tailnet.

```bash
fly apps create <app>
fly secrets set -a <app> OPENROUTER_API_KEY=sk-or-... TS_AUTHKEY=tskey-auth-...
fly volumes create ts_state --region <nearest> --size 1 -a <app>
fly deploy -a <app> --ha=false
```

- Pick `<nearest>` close to the user — every TLS handshake pays the round trip.
- The volume at `/var/lib/tailscale` persists the node identity + cert across restarts.
- Optional: set `TS_HOSTNAME` (default `hermes`) to name the tailnet node.
- Model defaults to `deepseek/deepseek-v4-flash`; change it in `hermes_config.yaml` before deploy if desired.

After deploy, `fly logs -a <app>` should show Tailscale joining and the cert
provisioning. The node is reachable at `wss://<node>.<your-tailnet>.ts.net/`.

## Phase 2 — Connect a client (recommended)

Recommend **Thunderbolt** (Mozilla Thunderbird's open-source ACP client; web,
desktop, iOS, Android). With the device on the same tailnet:

1. **Settings → Agents → Add Custom Agent**
2. **Name:** `Hermes`
3. **URL:** `wss://<node>.<your-tailnet>.ts.net/` — must match the node's name
   (that's what the TLS cert is issued for).
4. Save and start chatting.

iOS requires `wss://`, which needs HTTPS Certificates enabled on the tailnet (Phase 0).

## Phase 3 — Proton mail / calendar / contacts (optional)

Ask first. Enables the `proton` skill via a local hydroxide bridge
(IMAP/SMTP/CalDAV/CardDAV on localhost).

1. Mint a hydroxide `auth.json` **locally**, once — have the user run
   `! hydroxide auth` and follow its prompts (Proton login + bridge password).
2. base64-encode it and set the secret:
   ```bash
   fly secrets set -a <app> HYDROXIDE_AUTH_B64="$(base64 -w0 ~/.config/hydroxide/auth.json)"
   ```
3. Redeploy: `fly deploy -a <app> --ha=false`. Presence of `HYDROXIDE_AUTH_B64`
   auto-starts the bridge.

## Phase 4 — Matrix / Beeper chat (optional)

Ask first. Lets the user talk to Hermes from Beeper (a hosted Matrix
homeserver). The Matrix gateway runs alongside the ACP bridge — both work at once.

1. **Make a dedicated bot account.** Sign up a *second* Beeper account with its
   own email — that's the bot. (Don't use the main account, or the bot would see
   and could reply in every bridged chat.) From the main account, start a chat
   with the bot so there's a room.
2. **Mint an access token** for the bot — have the user run
   `! python3 beeper_login.py --app <app>`, entering the bot's email then the
   6-digit code Beeper emails it. It prints `MATRIX_ACCESS_TOKEN`,
   `MATRIX_USER_ID`, `MATRIX_DEVICE_ID`, and a ready-to-paste `fly secrets set`
   line. Keep the token and device ID together (the device ID is tied to the
   bot's E2EE identity).
3. **Get the recovery key** from the bot account's **Beeper → Settings →
   Encryption** — it lets the bot cross-sign its own device so the user's client
   shares encryption sessions with it.
4. **Set the secrets** (`MATRIX_ENCRYPTION=true` is required — Beeper rooms are E2EE):
   ```bash
   fly secrets set -a <app> \
     MATRIX_HOMESERVER=https://matrix.beeper.com \
     MATRIX_ACCESS_TOKEN=syt_... \
     MATRIX_DEVICE_ID=ABCDEF... \
     MATRIX_ENCRYPTION=true \
     MATRIX_RECOVERY_KEY="EsT... bot account's Beeper recovery key" \
     MATRIX_ALLOWED_USERS=@your-main-user:beeper.com
   ```
   Lock `MATRIX_ALLOWED_USERS` down to the user's own main account.
5. **Deploy:** `fly deploy -a <app> --ha=false`. Within a few seconds
   `fly logs` shows `starting messaging gateway (...): matrix`. A DM to the bot
   gets a response to every message (no `@mention` needed). The crypto store
   persists at `/data/hermes/platforms/matrix/store`.

## Phase 5 — Notion (optional)

Ask first. Lights up the `ntn` CLI and the bundled `notion` skill.

```bash
fly secrets set -a <app> NOTION_API_KEY=secret_...   # aliased to NOTION_API_TOKEN internally
fly deploy -a <app> --ha=false
```

## Phase 6 — CSP vault sync (optional)

Ask first. Clones a remote [CSP](https://github.com/cjroth/csp) vault into
`/data/vault` and watches it. Needs **both** secrets or sync is skipped.

```bash
fly secrets set -a <app> \
  CTX_AUTH_KEY=<csp §10 enrollment secret> \
  CSP_REMOTE=wss://host[:port]
fly deploy -a <app> --ha=false
```

`CTX_AUTH_KEY` is CSP's pre-shared enrollment bearer secret (no fixed format);
on first boot `ctx` enrolls this node (key persisted at `/data/csp/id_ed25519`)
and clones the vault. Logs go to `/data/csp/csp.log`.

## Wrap up

Summarize what was enabled vs skipped, give the user the `wss://` URL for their
client, and note that skipped integrations can be added later by setting their
secrets and redeploying. A periodic restart (well within the ~90-day cert life)
re-provisions the TLS cert, since manual certs don't auto-renew.
