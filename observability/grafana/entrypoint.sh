#!/bin/sh
set -eu

# Railway mounts a new volume as root-owned. Grafana runs as uid 472 by
# default, so initialize the data directory before handing off to its runner.
mkdir -p /var/lib/grafana
chown -R 472:0 /var/lib/grafana

exec su -s /bin/sh grafana -c /run.sh
