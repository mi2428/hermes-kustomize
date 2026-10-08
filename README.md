# Hermes Agent on Kubernetes

A reusable Kustomize deployment for the official [Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/docker) image. The base runs one persistent gateway with an authenticated, cluster-internal API. The [dashboard](components/dashboard/) is optional; model, search, channel, storage, and network choices belong to the consuming deployment.

## Requirements

- Kubernetes with a StorageClass (or a pre-provisioned persistent volume), `kubectl`, and Kustomize.
- A model provider and credentials, plus a private backup destination for Hermes data.
- These resources in the same namespace as the Deployment:

| Resource | Purpose |
| --- | --- |
| PVC `hermes-data` | Persistent `/opt/data`; use a filesystem compatible with SQLite locking. |
| ConfigMap `hermes-managed` | Non-secret `config.yaml`, mounted at `/etc/hermes/config.yaml`. |
| Secret `hermes-runtime` | `API_SERVER_KEY` (random, at least 16 characters) and provider/channel keys. |
| ConfigMap `hermes-environment` | Optional non-secret image environment variables. |

The optional `components/soul/` also expects a `hermes-soul` ConfigMap containing a non-empty `SOUL.md`. Generate it from a file in your consuming repository as shown in [`examples/with-soul/`](examples/with-soul/). On each rollout, the component atomically copies that file to `/opt/data/SOUL.md` as UID 10000; it never touches `memories/USER.md` or `MEMORY.md`.

## Deploy

Use [`examples/basic/`](examples/basic/) as a template for the PVC and config, **not as a working deployment**: replace its `example.invalid` endpoint and model ID, supply real credentials through your secret manager, and select a StorageClass if your cluster has no default. Do not commit plaintext credentials.

Reference the base from your own overlay at a reviewed commit or immutable tag:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - github.com/YOUR_ORG/hermes-kustomize/base?ref=YOUR_IMMUTABLE_REF
  - pvc.yaml
configMapGenerator:
  - name: hermes-managed
    files: [config.yaml]
```

Provide `hermes-runtime` separately. Add a `hermes-environment` ConfigMap for additional **non-secret** image variables if needed; the base already reads both resources. Then build and apply your overlay:

```sh
kubectl kustomize path/to/your/overlay
kubectl apply -k path/to/your/overlay
kubectl port-forward svc/hermes 8642:8642
```

Authenticate API clients with `API_SERVER_KEY`; the agent is advertised at `http://127.0.0.1:8642/v1`. No Ingress or external load balancer is created. The optional dashboard example is [`examples/with-dashboard/`](examples/with-dashboard/): add `components/dashboard/` to your overlay, supply a [dashboard auth provider](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard#authentication-gated-mode), and use port 9119. Do not expose either service publicly without an appropriate authenticated HTTPS entrypoint.

For messaging, configure the selected channel in Hermes and put its token and user allowlist in `hermes-runtime`. [Telegram long polling](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram#webhook-mode) and [Slack Socket Mode](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/slack) need outbound internet access, not inbound NAT or an Ingress. Telegram webhook mode is different: it requires a public HTTPS endpoint.

## Configuration and operations

- [`hermes-managed`](https://hermes-agent.nousresearch.com/docs/user-guide/managed-scope) pins only the YAML keys it contains; the writable `/opt/data/config.yaml`, persona, memory, and sessions stay on the PVC. The init container rejects syntactically invalid managed YAML. Set model and web backend choices in the consumer's config, and keep keys in the Secret. See [Hermes provider](https://hermes-agent.nousresearch.com/docs/integrations/providers) and [web search](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search) settings.
- Hash-suffixed Kustomize-generated ConfigMaps restart the Pod when config changes. External stable-name ConfigMaps and updated Secrets need an explicit rollout restart; verify credentials afterward and avoid duplicate keys in the persisted `/opt/data/.env`.
- Keep one gateway per data volume. `Recreate` avoids overlapping Pods from this Deployment, but `ReadWriteOnce` is not a multi-writer lock. A PVC is not a backup: stop the gateway, back up all of `/opt/data` off-cluster, and test a restore before upgrading. Check the PV reclaim policy before deleting the claim.
- The gateway's API can run tools, including shell commands in the Pod. `ClusterIP` is not an access-control boundary; restrict callers with a NetworkPolicy where appropriate. The official image needs its root-owned s6 bootstrap; do not replace its entrypoint or force `runAsNonRoot` without testing the image.

## Verify

`bash scripts/check.sh` lints Dockerfiles/shell/Python/YAML, type-checks the add-on, builds all Kustomize examples, and checks Kubernetes schemas without deploying; verify your model and channels in the target environment.
