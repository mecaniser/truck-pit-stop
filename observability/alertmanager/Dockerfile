FROM prom/alertmanager:v0.28.1

COPY alertmanager.yml.template /etc/alertmanager/alertmanager.yml.template
COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
