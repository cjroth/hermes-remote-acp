FROM docker.io/nousresearch/hermes-agent:latest

# Install the stdio-to-ws ACP WebSocket bridge
RUN npm install -g stdio-to-ws

# Seed hermes config with OpenRouter settings
# /opt/data is HERMES_HOME, owned by hermes:hermes
COPY --chown=hermes:hermes hermes_config.yaml /opt/data/config.yaml

# Bridge startup script — executed as hermes user via s6-setuidgid in main-wrapper.sh
COPY bridge.sh /bridge.sh
RUN chmod +x /bridge.sh

# Railway injects PORT at runtime
ENV PORT=3000

# main-wrapper.sh sees /bridge.sh as an executable and runs:
#   exec s6-setuidgid hermes /bridge.sh
CMD ["/bridge.sh"]
