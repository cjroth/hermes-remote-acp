FROM docker.io/nousresearch/hermes-agent:latest

# Install the stdio-to-ws ACP WebSocket bridge.
# Patch it to honor a WS_HOST env var so we can bind the WebSocket server to
# loopback only (the CLI exposes no --host). With WS_HOST unset it binds all
# interfaces as before; bridge.sh sets WS_HOST=127.0.0.1 for the tailnet-only
# lockdown. The patch is idempotent-checked so the build fails loudly if a
# future stdio-to-ws version changes this line.
RUN npm install -g stdio-to-ws \
    && f="$(npm root -g)/stdio-to-ws/dist/stdio-to-ws.js" \
    && grep -q 'new WebSocketServer({' "$f" \
    && sed -i 's#new WebSocketServer({#new WebSocketServer({ host: process.env.WS_HOST || undefined,#' "$f" \
    && grep -q "process.env.WS_HOST" "$f"

# --- Tailscale (userspace networking — no TUN/NET_ADMIN needed) ---------------
# Pinned for reproducible builds. Arch is detected so the image builds on both
# amd64 (Railway builders) and arm64 (local).
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
    rm -rf /tmp/ts.tgz "/tmp/tailscale_${TAILSCALE_VERSION}_${ts_arch}"; \
    mkdir -p /var/run/tailscale

# Tailscale s6 services: tailscaled (longrun, root) + tailscale-up (oneshot that
# joins the talnet and runs `tailscale serve`). Both are added to the `user`
# bundle so s6-overlay supervises them alongside the bridge CMD.
COPY s6/tailscaled/         /etc/s6-overlay/s6-rc.d/tailscaled/
COPY s6/tailscale-up/       /etc/s6-overlay/s6-rc.d/tailscale-up/
RUN chmod +x /etc/s6-overlay/s6-rc.d/tailscaled/run /etc/s6-overlay/s6-rc.d/tailscale-up/run; \
    touch /etc/s6-overlay/s6-rc.d/user/contents.d/tailscaled \
          /etc/s6-overlay/s6-rc.d/user/contents.d/tailscale-up

# Seed hermes config with OpenRouter settings
# /opt/data is HERMES_HOME, owned by hermes:hermes
COPY --chown=hermes:hermes hermes_config.yaml /opt/data/config.yaml

# Bridge startup script — executed as hermes user via s6-setuidgid in main-wrapper.sh
COPY bridge.sh /bridge.sh
RUN chmod +x /bridge.sh

# Railway injects PORT at runtime. The bridge binds this port; it is exposed to
# the tailnet ONLY via `tailscale serve` (the Railway public domain is removed),
# so there is no public ingress.
ENV PORT=3000

# main-wrapper.sh sees /bridge.sh as an executable and runs:
#   exec s6-setuidgid hermes /bridge.sh
CMD ["/bridge.sh"]
