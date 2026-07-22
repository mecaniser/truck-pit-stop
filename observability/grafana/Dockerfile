FROM grafana/grafana:12.0.2

COPY provisioning /etc/grafana/provisioning
COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

USER root

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
