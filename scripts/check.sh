#!/usr/bin/env bash
set -euo pipefail

shellcheck -x -S warning scripts/*.sh
bash -n scripts/*.sh
shfmt -d -i 2 -ci scripts/*.sh
yamllint base/*.yaml components/dashboard/*.yaml examples/basic/*.yaml examples/with-dashboard/*.yaml
yq -r '.spec.template.spec.initContainers[0].command[2]' base/deployment.yaml |
  python3 -c 'import ast, sys; ast.parse(sys.stdin.read())'
yq -r '.spec.template.spec.containers[0].readinessProbe.exec.command[2]' base/deployment.yaml |
  python3 -c 'import ast, sys; ast.parse(sys.stdin.read())'
yq -e 'select(.kind == "Deployment") | .spec.template.spec.initContainers[0].image == .spec.template.spec.containers[0].image and (.spec.template.spec.containers[0].image | test("@sha256:[0-9a-f]{64}$"))' base/deployment.yaml >/dev/null

for path in base examples/basic examples/with-dashboard; do
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

# The reusable base must never choose a model, search backend, or cluster.
if kustomize build base | grep -Ei 'sakura|brave|kimi|example\.invalid|storageClassName|nodeSelector'; then
  exit 1
fi
