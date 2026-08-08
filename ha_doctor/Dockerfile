FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache python3 py3-yaml py3-websocket-client

WORKDIR /app
COPY app.py scanner.py scanner_patch.py scanner_v031.py scanner_v032.py scanner_v040.py scanner_v041.py registry_analysis.py rules.py redaction.py ./
COPY static ./static
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
