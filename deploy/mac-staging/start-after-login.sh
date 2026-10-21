#!/bin/sh
# User-login recovery only: FileVault must be unlocked locally after a reboot.
set -eu
export PATH=/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin
ROOT="$HOME/dieselbridge-staging"
# launchd runs only one instance of this job; no other environment is touched.
docker desktop start --timeout 60
cd "$ROOT/source"
docker compose --env-file ../private/staging.env -f deploy/mac-staging/compose.yaml up -d gateway
docker compose --env-file ../private/staging.env -f deploy/mac-staging/compose.yaml restart gateway
attempt=0
until curl --fail --silent --connect-timeout 2 --max-time 5 http://127.0.0.1:18080/health/ready; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 12 ] || exit 1
    sleep 5
done
printf '\nStaging recovered after login at %s\n' "$(date -u +%FT%TZ)"
