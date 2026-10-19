ARG HERMES_BASE_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_BASE_IMAGE}

RUN uv pip install --python /opt/hermes/.venv/bin/python 'ddgs==9.16.0' 'primp==2.0.1' 'lxml==6.1.3'
