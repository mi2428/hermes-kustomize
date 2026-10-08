# Web search router

Optional Hermes search provider: DDGS first; on rate limits, rotate across keyed Brave, Tavily, Exa, Firecrawl, and Parallel. Each provider is tried at most once per request. DDGS cools down for five minutes and exhausted keys for one hour; if all are unavailable, return an error immediately. Other failures stop rather than silently spending another provider's credits. Rotation and cooldowns reset on restart.

## Use

See [`examples/with-search-router/`](../../examples/with-search-router/). The official image lacks `ddgs`: build `docker build -f addons/web-search-router/Dockerfile -t hermes-agent-web-search-router:local .`, publish the image, then pin **all** init and main containers to its digest. The example's `:local` tag is a placeholder.

Provide `BRAVE_SEARCH_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`, and `PARALLEL_API_KEY` in the same-namespace `hermes-runtime` Secret. Set `web.search_backend: web-search-router`, `web.keyless_fallback: false`, and `web.keyless_rescue: false` in managed config. Missing keys prevent startup. Extraction is separate; the example uses Tavily and spends its shared credits.

This router **does not cap spending**: disable overage billing at each provider. DDGS errors are textual, so an unrecognized throttle returns an error rather than using a keyed provider. Verify actual provider behavior before deployment. Run `bash scripts/check.sh` for static checks; `test_provider.py` exercises routing offline against the built image.
