# API reference and observability

## API reference

`/docs` serves the API reference with [Scalar](https://scalar.com), branded with the Copier
answers `brand_name` and `brand_primary_color`: page title, favicon (the same mark as the
frontend), accent color, no vendor link. Swagger UI and ReDoc are switched off. The reference
and `openapi.json` exist in `local`, `development` and `staging`, not in `production`.

The page makes no calls to third parties. Telemetry, the AI agent, the hosted fonts, the
request proxy and the button that opens Scalar's client are disabled, and the page carries
its own Content Security Policy, built from the rendered HTML: scripts only from the pinned
Scalar bundle and the page's inline script (by hash), connections only to the API itself.

The bundle comes from jsDelivr, pinned to an exact version in `API_DOCS_SCALAR_JS_URL`. For
installations without internet access, serve a copy of
`@scalar/api-reference/dist/browser/standalone.js` from your infrastructure and point the
setting at it: the policy follows the setting.

## Logs

Logs are JSON lines on standard output, ready for Loki, Elasticsearch or CloudWatch
(`LOG_FORMAT=text` for a terminal). Each record carries `timestamp`, `level`, `logger`,
`message`, any `extra=` fields, the `request_id` of the HTTP request and, when tracing is on,
`trace_id` and `span_id`. E-mail addresses, tokens and passwords are redacted for every logger.

The `request_id` is the `X-Request-ID` response header and the `request_id` field of Problem
Details errors, so an error reported by a client leads to its log lines. A request id sent by
the client is kept only when it is a plain identifier (letters, digits, `._:-`, at most 128
characters).

## Traces

With `OTEL_EXPORTER_OTLP_ENDPOINT` set (for example `http://otel-collector:4318`), traces are
exported over OTLP/HTTP to any OpenTelemetry backend: incoming requests (health checks and
metrics excluded), SQL queries, outgoing httpx calls and Redis commands.
`OTEL_TRACES_SAMPLE_RATIO` samples a share of the traces, following the caller's decision
when the request carries one. Without an endpoint nothing is instrumented.

Projects generated with `logfire` use Logfire for tracing instead, which is itself built on
OpenTelemetry.

## Metrics

`/metrics` exposes Prometheus metrics: request counts and latencies per route, plus the
standard process metrics. Set `PROMETHEUS_AUTH_TOKEN` to require a bearer token when the
endpoint is reachable from outside.

## Security headers

Every response carries a Content Security Policy, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`.
