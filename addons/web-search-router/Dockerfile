ARG HERMES_BASE_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_BASE_IMAGE}

# hadolint ignore=DL3013
RUN /opt/hermes/.venv/bin/python -m ensurepip --upgrade \
 && /opt/hermes/.venv/bin/python -m pip install --no-cache-dir \
    ddgs primp lxml pyyaml
