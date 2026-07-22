# Production Observability

The Railway production environment runs three private monitoring services:

- Prometheus scrapes the API every 15 seconds and retains time-series data on its volume.
- Alertmanager groups sustained alerts and sends firing and resolved events to the configured operations webhook.
- Grafana reads Prometheus privately and presents the provisioned production-performance dashboard.

## Railway variables

| Service | Required variables |
| --- | --- |
| `diesel-bridge-network` | `METRICS_AUTH_TOKEN` |
| `prometheus` | `METRICS_AUTH_TOKEN`, `API_PRIVATE_HOST`, `API_PORT` |
| `alertmanager` | `ALERT_WEBHOOK_URL` |
| `grafana` | `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD` |

Set `API_PRIVATE_HOST` to the API service's Railway private hostname and `API_PORT` to its listening port. Give Prometheus a Railway volume mounted at `/prometheus`, Alertmanager a volume at `/alertmanager`, and Grafana a volume at `/var/lib/grafana`.

## Alert policy

- API unavailable for 2 minutes: critical.
- API p95 at or above 1.5 seconds for 2 minutes: critical.
- API p95 at or above 750 milliseconds for 5 minutes: warning.
- API 5xx rate at or above 1% for 5 minutes: critical.
- Database query p95 at or above 250 milliseconds for 5 minutes: warning.

The collector excludes health checks, its own metrics endpoint, and the performance dashboard endpoint from latency alerts. Thresholds are starting production guardrails; after two weeks of representative tenant traffic, tune them against the observed baseline.
