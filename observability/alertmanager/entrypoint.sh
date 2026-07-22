#!/bin/sh
set -eu

if [ -z "${ALERT_WEBHOOK_URL:-}" ]; then
  echo "Missing required environment variable: ALERT_WEBHOOK_URL" >&2
  exit 1
fi

escaped_webhook_url=$(printf '%s' "$ALERT_WEBHOOK_URL" | sed 's/[&|]/\\&/g')
sed "s|\${ALERT_WEBHOOK_URL}|$escaped_webhook_url|g" \
  /etc/alertmanager/alertmanager.yml.template > /etc/alertmanager/alertmanager.yml

exec /bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/alertmanager
