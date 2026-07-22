#!/bin/sh
set -eu

required_variables="METRICS_AUTH_TOKEN API_PRIVATE_HOST API_PORT"
for variable in $required_variables; do
  eval "value=\${$variable:-}"
  if [ -z "$value" ]; then
    echo "Missing required environment variable: $variable" >&2
    exit 1
  fi
done

escaped_token=$(printf '%s' "$METRICS_AUTH_TOKEN" | sed 's/[&|]/\\&/g')
escaped_host=$(printf '%s' "$API_PRIVATE_HOST" | sed 's/[&|]/\\&/g')
escaped_port=$(printf '%s' "$API_PORT" | sed 's/[&|]/\\&/g')

sed \
  -e "s|\${METRICS_AUTH_TOKEN}|$escaped_token|g" \
  -e "s|\${API_PRIVATE_HOST}|$escaped_host|g" \
  -e "s|\${API_PORT}|$escaped_port|g" \
  /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml

exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.enable-lifecycle
