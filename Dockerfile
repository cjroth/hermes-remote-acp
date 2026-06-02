FROM docker.io/nousresearch/hermes-agent:latest

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
