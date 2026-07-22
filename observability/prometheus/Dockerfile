FROM prom/prometheus:v3.5.0

COPY prometheus.yml.template /etc/prometheus/prometheus.yml.template
COPY alerts.yml /etc/prometheus/alerts.yml
COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
