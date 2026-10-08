ARG HERMES_BASE_IMAGE=nousresearch/hermes-agent:v2026.9.24@sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7
FROM ${HERMES_BASE_IMAGE}

ARG TARGETARCH
ENV AGENT_BROWSER_EXECUTABLE_PATH=/opt/hermes/browser/chrome
RUN if [ "$TARGETARCH" != "amd64" ]; then \
      printf 'Chrome for Testing is not available for linux/%s in this add-on\n' "$TARGETARCH" >&2; \
      exit 1; \
    fi \
 && apt-get update \
 && apt-get install --yes --no-install-recommends sudo=1.9.16p2-3+deb13u2 \
 && npm install --global --no-audit --no-fund --allow-scripts=agent-browser agent-browser@0.38.2 \
 && agent-browser install --with-deps \
 && mkdir -p /opt/hermes/browser \
 && for chrome in /root/.agent-browser/browsers/chrome-*/chrome /root/.agent-browser/browsers/chrome-*/chrome-linux64/chrome; do \
      if [ -x "$chrome" ]; then cp -a "$(dirname "$chrome")/." /opt/hermes/browser/; break; fi; \
    done \
 && chmod -R a+rX /opt/hermes/browser \
 && test -x "$AGENT_BROWSER_EXECUTABLE_PATH" \
 && SUDO_FORCE_REMOVE=yes apt-get purge --yes --auto-remove sudo \
 && install -d -m 0700 -o 10000 -g 10000 "$XDG_RUNTIME_DIR" \
 && rm -rf /var/lib/apt/lists/* /root/.agent-browser/browsers
