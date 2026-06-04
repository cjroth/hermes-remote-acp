# --- Build the CSP `ctx` CLI (Context Sync Protocol) -------------------------
# Built in a throwaway Rust stage and copied into the final image as a single
# self-contained binary, so the runtime image carries no Rust toolchain.
# Pinned to a commit for reproducible builds (bump CSP_REV to upgrade);
# `--locked` uses the repo's committed Cargo.lock so transitive deps don't
# drift. `ring` (0.17) ships pregenerated asm, so the stock Rust image's gcc
# is the only build dep needed.
FROM docker.io/library/rust:1-bookworm AS cspbuild
ARG CSP_GIT=https://github.com/cjroth/csp.git
ARG CSP_REV=57f0ccf089599cb3f583e4de2fcca9c1f63c2406
RUN cargo install --git "$CSP_GIT" --rev "$CSP_REV" --locked ctx --root /out

# --- Build hydroxide (self-hosted ProtonMail bridge, CalDAV-enabled fork) -----
# Throwaway Go stage; the final image carries only the static binary (no Go
# toolchain). Our fork adds CalDAV support (PR #282 rebased onto upstream +
# go-webdav v0.7) plus event create/read/time-range fixes. Pinned to a commit
# for reproducible builds (bump HYDROXIDE_REV to upgrade). CGO disabled so the
# binary is fully static and runs in the runtime image as-is.
FROM docker.io/library/golang:1.24-bookworm AS hydroxidebuild
ARG HYDROXIDE_GIT=https://github.com/cjroth/hydroxide.git
ARG HYDROXIDE_REV=575ee6a52f7d8bc1af6451b719bc36528e1b89f3
RUN git clone "$HYDROXIDE_GIT" /src \
    && cd /src && git checkout "$HYDROXIDE_REV" \
    && CGO_ENABLED=0 go build -trimpath -o /out/hydroxide ./cmd/hydroxide

FROM docker.io/nousresearch/hermes-agent:latest

# CSP `ctx` CLI (built above) — keeps /data/vault synced with a remote CSP
# listener (clone-on-first-boot, then watch). See the CSP block in init.sh.
COPY --from=cspbuild /out/bin/ctx /usr/local/bin/ctx

# hydroxide (built above) — self-hosted ProtonMail bridge. init.sh runs
# `hydroxide serve` (IMAP/SMTP/CardDAV/CalDAV on 127.0.0.1) when seeded with a
# stored credential file via the HYDROXIDE_AUTH_B64 secret. See the hydroxide
# block in init.sh.
COPY --from=hydroxidebuild /out/hydroxide /usr/local/bin/hydroxide

# `proton` skill — teaches the agent to use the hydroxide bridge (mail/calendar/
# contacts) via a stdlib-only helper script. Bundled alongside the image's other
# skills so it's picked up by the skill loader.
COPY skills/proton /opt/hermes/skills/communication/proton

# Custom stdio<->WebSocket bridge (bridge.js). It terminates TLS itself (using
# the Tailscale cert) because `tailscale serve --https` wedges in userspace
# netstack; Tailscale just does raw TCP passthrough to it. Needs the `ws` pkg.
RUN mkdir -p /opt/bridge
COPY bridge.js /opt/bridge/bridge.js
RUN cd /opt/bridge && npm install ws@8

# Notion's official `ntn` CLI — the bundled Hermes `notion` skill prefers it
# over raw HTTP (shorter syntax, file uploads, Workers). Node ships in the base
# image. NOTION_KEYRING=0 keeps it headless (no OS keychain); init.sh aliases
# NOTION_API_TOKEN from NOTION_API_KEY at runtime.
RUN npm install -g ntn
ENV NOTION_KEYRING=0

# --- Tailscale (kernel TUN where allowed, userspace fallback) -----------------
# Pinned for reproducible builds. Arch detected so it builds on amd64 + arm64.
ARG TAILSCALE_VERSION=1.98.4
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) ts_arch=amd64 ;; \
      arm64) ts_arch=arm64 ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_${ts_arch}.tgz" -o /tmp/ts.tgz; \
    tar -xzf /tmp/ts.tgz -C /tmp; \
    mv "/tmp/tailscale_${TAILSCALE_VERSION}_${ts_arch}/tailscale"  /usr/local/bin/tailscale; \
    mv "/tmp/tailscale_${TAILSCALE_VERSION}_${ts_arch}/tailscaled" /usr/local/bin/tailscaled; \
    rm -rf /tmp/ts.tgz "/tmp/tailscale_${TAILSCALE_VERSION}_${ts_arch}"

# HERMES_HOME lives on the persistent volume (/data/hermes), overriding the base
# image's /opt/data so the agent's sessions/memory/skills survive restarts.
ENV HERMES_HOME=/data/hermes

# Hermes config (OpenRouter provider + model). Staged outside the volume path so
# the mount can't shadow it; init.sh seeds it into /data/hermes on boot.
COPY hermes_config.yaml /opt/seed/config.yaml

# Single entrypoint — orchestrates tailscaled + serve + bridge WITHOUT s6
# (s6-overlay needs PID 1, which Fly.io's init doesn't provide). The bridge is
# reachable ONLY via `tailscale serve` over the tailnet; no public ingress.
COPY init.sh /init.sh
RUN chmod +x /init.sh

ENTRYPOINT ["/init.sh"]
CMD []
