FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache python3 py3-yaml py3-websocket-client

WORKDIR /app

# Copy every Python module from the App build context. This deliberately avoids
# the fragile hand-maintained module list that caused the 0.6 startup failure.
COPY *.py ./
COPY static ./static
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
