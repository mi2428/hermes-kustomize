# Local browser

Build the pinned Hermes image with a pinned `agent-browser` CLI and Chromium in the image layer; no Docker socket or runtime package downloads are needed in the Pod. Use `components/local-browser/` only with the resulting image. The component provides a 512-MiB in-memory `/dev/shm` and rejects an image without `agent-browser` at startup. It does not choose a model, browser provider, or credentials.

```sh
docker build -f addons/local-browser/Dockerfile -t hermes-agent-local-browser:local .
```

To combine it with the independent DDGS search add-on, build that image first and pass it as the base; [`examples/with-browser-and-search/`](../../examples/with-browser-and-search/) shows the matching Kustomize components:

```sh
docker build -f addons/web-search-router/Dockerfile -t hermes-agent-web-search-router:local .
docker build -f addons/local-browser/Dockerfile \
  --build-arg HERMES_BASE_IMAGE=hermes-agent-web-search-router:local \
  -t hermes-agent-browser-search:local .
```

Pin the published **linux/amd64** image by digest in the consuming overlay for **all** containers and add `components/local-browser/`. Chrome for Testing does not ship Linux ARM64 binaries; this add-on fails at build time for that architecture rather than producing an unusable image. The pinned Hermes browser resolver reads only the writable profile config; this add-on fails closed unless its one-line fix can make it read the managed configuration as well. Set `browser.cloud_provider: local` in the consumer's managed config so existing cloud keys cannot override local Chrome. `browser.backend: "off"` selects the built-in `browser_*` tools instead of downloading Browser Use CLI on demand. Enable the `browser` toolset separately and keep `browser.use_real_profile: false`. A browser running beside a gateway can still reach the Pod's network and data; configure isolation and tool approvals in the consuming environment.
