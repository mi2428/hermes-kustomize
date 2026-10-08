#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
image=$(yq -r '.spec.template.spec.containers[0].image' base/deployment.yaml)
validate=$(yq -r '.spec.template.spec.initContainers[0].command[2]' base/deployment.yaml)
ready=$(yq -r '.spec.template.spec.containers[0].readinessProbe.exec.command[2]' base/deployment.yaml)
name="hermes-kustomize-smoke-$(date +%s)-$$"
if docker volume inspect "$name" >/dev/null 2>&1 || docker container inspect "$name" >/dev/null 2>&1; then
  exit 1
fi
docker volume create "$name" >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1 || :; docker volume rm "$name" >/dev/null 2>&1 || :' EXIT

managed() {
  docker run --rm --network none \
    --mount "type=bind,src=$PWD/$1,dst=/managed/config.yaml,readonly" \
    --entrypoint /opt/hermes/.venv/bin/python "$image" -c "$validate"
}

managed examples/basic/config.yaml
if managed tests/fixtures/invalid-config.txt 2>/dev/null; then
  printf 'Malformed managed config was accepted\n' >&2
  exit 1
fi

start() {
  docker run -d --network none --name "$name" \
    --mount "type=volume,src=$name,dst=/opt/data" \
    --mount "type=bind,src=$PWD/$1,dst=/etc/hermes/config.yaml,readonly" \
    -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 \
    -e API_SERVER_KEY="$2" -e MODEL_API_KEY=smoke-placeholder \
    "${@:3}" "$image" gateway run >/dev/null
  for ((attempt = 0; attempt < 60; attempt++)); do
    if docker exec "$name" /opt/hermes/.venv/bin/python -c "$ready" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  printf 'Hermes failed readiness\n' >&2
  exit 1
}

stop() {
  docker stop -t 30 "$name" >/dev/null
  docker rm "$name" >/dev/null
}

start examples/basic/config.yaml smoke-key-first-not-a-secret-123456 \
  -e API_SERVER_MODEL_NAME=example-hermes
test "$(docker exec "$name" hermes config get model.default)" = REPLACE_WITH_MODEL_ID
test "$(docker exec "$name" hermes config get web.keyless_fallback)" = false
docker exec "$name" /opt/hermes/.venv/bin/python -c \
  'import json, urllib.request
request = urllib.request.Request("http://127.0.0.1:8642/v1/models", headers={"Authorization": "Bearer smoke-key-first-not-a-secret-123456"})
assert json.load(urllib.request.urlopen(request, timeout=4))["data"][0]["id"] == "example-hermes"'
docker exec "$name" /opt/hermes/.venv/bin/python -c \
  'from pathlib import Path; Path("/opt/data/smoke-marker").touch()'
stop

start tests/fixtures/next-config.yaml smoke-key-second-not-a-secret-12345 \
  -e HERMES_DASHBOARD=1 -e HERMES_DASHBOARD_HOST=0.0.0.0 \
  -e HERMES_DASHBOARD_BASIC_AUTH_USERNAME=smoke-only \
  -e HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=not-a-real-password-12345 \
  -e HERMES_DASHBOARD_BASIC_AUTH_SECRET=smoke-only-cookie-secret-1234567890
test "$(docker exec "$name" hermes config get model.default)" = NEXT_MODEL
docker exec "$name" /opt/hermes/.venv/bin/python -c \
  'from pathlib import Path; assert Path("/opt/data/smoke-marker").is_file()'
docker exec "$name" /opt/hermes/.venv/bin/python -c \
  'import json, urllib.error, urllib.request
url = "http://127.0.0.1:8642/v1/models"
for key, expected in (("smoke-key-first-not-a-secret-123456", 401), ("smoke-key-second-not-a-secret-12345", 200)):
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
    try:
        response = urllib.request.urlopen(request, timeout=4)
        status = response.status
        response.close()
    except urllib.error.HTTPError as error:
        status = error.code
    assert status == expected, (status, expected)
dashboard = json.load(urllib.request.urlopen("http://127.0.0.1:9119/api/status", timeout=4))
assert dashboard["auth_required"] is True and "basic" in dashboard["auth_providers"]'
stop

docker run -d --rm --network none --name "$name" \
  --mount type=volume,dst=/opt/data \
  --mount "type=bind,src=$PWD/examples/basic/config.yaml,dst=/etc/hermes/config.yaml,readonly" \
  -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 \
  -e API_SERVER_KEY=smoke-key-no-dashboard-auth-12345 \
  -e HERMES_DASHBOARD=1 -e HERMES_DASHBOARD_HOST=0.0.0.0 \
  "$image" gateway run >/dev/null
api_up=false
for ((attempt = 0; attempt < 60; attempt++)); do
  if docker exec "$name" /opt/hermes/.venv/bin/python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8642/health", timeout=4)' >/dev/null 2>&1; then
    api_up=true
    break
  fi
  sleep 2
done
if [[ $api_up != true ]]; then
  printf 'Gateway did not start in missing-auth test\n' >&2
  exit 1
fi
sleep 5
if docker exec "$name" /opt/hermes/.venv/bin/python -c "$ready" >/dev/null 2>&1; then
  printf 'Dashboard without authentication passed readiness\n' >&2
  exit 1
fi
docker stop "$name" >/dev/null
printf 'Managed config updates, persistent state, key rotation and gated dashboard passed\n'
