FROM prom/alertmanager:v0.28.1

COPY alertmanager.yml.template /etc/alertmanager/alertmanager.yml.template
COPY --chmod=755 entrypoint.sh /app/entrypoint.sh

# Railway mounts a root-owned persistent volume at /alertmanager. The upstream
# image runs as nobody, which prevents Alertmanager from persisting silences and
# notification state on that volume.
USER root

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
