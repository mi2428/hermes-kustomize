#!/usr/bin/env bash
set -euo pipefail

shellcheck -x -S warning scripts/*.sh
bash -n scripts/*.sh
shfmt -d -i 2 -ci scripts/*.sh
hadolint addons/web-search-router/Dockerfile addons/local-browser/Dockerfile
yamllint base/*.yaml components/dashboard/*.yaml components/soul/*.yaml components/local-browser/*.yaml addons/web-search-router/*.yaml addons/web-search-router/plugin/*.yaml examples/basic/*.yaml examples/with-dashboard/*.yaml examples/with-soul/*.yaml examples/with-search-router/*.yaml examples/with-local-browser/*.yaml examples/with-browser-and-search/*.yaml
ruff check addons/web-search-router/plugin addons/web-search-router/test_provider.py
ruff check addons/local-browser/patch_managed_browser.py
ruff check --select ANN addons/web-search-router/plugin addons/web-search-router/test_provider.py
ruff check --select D --ignore D107,D203,D213 addons/web-search-router/plugin
ruff format --check addons/web-search-router/plugin addons/web-search-router/test_provider.py
ruff format --check addons/local-browser/patch_managed_browser.py
pyright -p addons/web-search-router/pyrightconfig.json
for source in addons/web-search-router/plugin/*.py addons/web-search-router/test_*.py; do
  python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())' "$source"
done
yq -r '.spec.template.spec.initContainers[] | select(.name == "validate-search-router") | .command[2]' addons/web-search-router/deployment.yaml |
  python3 -c 'import ast, sys; ast.parse(sys.stdin.read())'
yq -r '.spec.template.spec.initContainers[0].command[2]' base/deployment.yaml |
  python3 -c 'import ast, sys; ast.parse(sys.stdin.read())'
yq -r '.spec.template.spec.initContainers[0].command[2]' components/soul/deployment.yaml |
  shellcheck -s sh -
yq -r '.spec.template.spec.containers[0].readinessProbe.exec.command[2]' base/deployment.yaml |
  python3 -c 'import ast, sys; ast.parse(sys.stdin.read())'
yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[0].image == .spec.template.spec.containers[0].image and (.spec.template.spec.containers[0].image | test("@sha256:[0-9a-f]{64}$"))' base/deployment.yaml >/dev/null

for path in base examples/basic examples/with-dashboard examples/with-soul examples/with-search-router examples/with-local-browser examples/with-browser-and-search; do
  kustomize build "$path" | kubeconform -strict -summary
done

if kustomize build examples/basic |
  yq -e 'select(.kind == "Service") | .spec.ports[] | select(.name == "dashboard")' >/dev/null 2>&1; then
  printf 'Dashboard port leaked into the basic example\n' >&2
  exit 1
fi
kustomize build examples/with-dashboard |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.containers[0].env[] | select(.name == "HERMES_DASHBOARD" and .value == "1")' >/dev/null
kustomize build examples/with-dashboard |
  yq -e 'select(.kind == "Service") | .spec.ports[] | select(.name == "dashboard" and .port == 9119)' >/dev/null
kustomize build examples/basic |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.containers[0].envFrom[] | select(.configMapRef.name | test("^hermes-environment-"))' >/dev/null
kustomize build examples/with-search-router |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.containers[0].volumeMounts[] | select(.mountPath == "/opt/hermes/plugins/web/web_search_router")' >/dev/null
kustomize build examples/with-search-router |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[] | select(.name == "validate-search-router" and .image == "hermes-agent-web-search-router:local")' >/dev/null
kustomize build examples/with-search-router |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[0].image == .spec.template.spec.containers[0].image' >/dev/null
kustomize build examples/with-soul |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[] | select(.name == "install-soul")' >/dev/null
kustomize build examples/with-soul |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.volumes[] | select(.name == "soul" and (.configMap.name | test("^hermes-soul-")))' >/dev/null
kustomize build examples/with-local-browser |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[] | select(.name == "validate-local-browser" and .image == "hermes-agent-local-browser:local")' >/dev/null
kustomize build examples/with-local-browser |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.containers[] | select(.name == "hermes") | .volumeMounts[] | select(.name == "browser-shm" and .mountPath == "/dev/shm")' >/dev/null
kustomize build examples/with-browser-and-search |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[] | select(.name == "validate-local-browser" and .image == "hermes-agent-browser-search:local")' >/dev/null
kustomize build examples/with-browser-and-search |
  yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[] | select(.name == "validate-search-router" and .image == "hermes-agent-browser-search:local")' >/dev/null

# The reusable base must never choose a model, search backend, or cluster.
if kustomize build base | grep -Ei 'sakura|brave|kimi|example\.invalid|storageClassName|nodeSelector'; then
  exit 1
fi
