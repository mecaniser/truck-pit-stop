#!/usr/bin/env bash
# Run a development environment that cannot collide with anyone else's.
#
# Two agents working the same repo kept landing on one stack: the dev compose
# file hardcodes container names and ports, so the second `up` either fails or
# adopts the first one's containers. The result was an API on :8000 serving one
# worktree while a frontend on :5174 served another and called it — a mismatch
# with no symptom until an endpoint 404s.
#
#   dev-env.sh up        start API (+ optionally web) for THIS worktree
#   dev-env.sh down      stop this worktree's API
#   dev-env.sh status    show every environment on this machine, and its branch
#   dev-env.sh logs      follow this worktree's API logs
#   dev-env.sh db-clone  give this worktree its own copy of the dev database
#
# Config comes from .dev-env in the worktree root (gitignored), or the defaults
# below. Each worktree wants its own ports, database and Redis index.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -f .dev-env ] && . ./.dev-env

# Default the environment name to the worktree directory, so two worktrees never
# collide by accident and `status` shows something recognisable.
ENV_NAME="${DIESELBRIDGE_ENV_NAME:-$(basename "$ROOT" | tr -c 'A-Za-z0-9_.-' '-' | cut -c1-30)}"
API_PORT="${DIESELBRIDGE_API_PORT:-8001}"
WEB_PORT="${DIESELBRIDGE_WEB_PORT:-5174}"
DB_NAME="${DIESELBRIDGE_LOCAL_DB_NAME:-truckpitstop_${ENV_NAME//-/_}}"
REDIS_DB="${DIESELBRIDGE_REDIS_DB:-1}"
SOURCE_DB="${DIESELBRIDGE_SOURCE_DB:-truckpitstop}"
PG_CONTAINER="${DIESELBRIDGE_PG_CONTAINER:-dieselbridge_postgres}"

export DIESELBRIDGE_ENV_NAME="$ENV_NAME" DIESELBRIDGE_API_PORT="$API_PORT" \
       DIESELBRIDGE_WEB_PORT="$WEB_PORT" DIESELBRIDGE_LOCAL_DB_NAME="$DB_NAME" \
       DIESELBRIDGE_REDIS_DB="$REDIS_DB"

COMPOSE=(docker compose -p "dieselbridge-$ENV_NAME" -f docker-compose.parallel.yml)

psql_pg() { docker exec "$PG_CONTAINER" psql -U dieselbridge -d "${1:-postgres}" "${@:2}"; }

cmd_db_clone() {
  if psql_pg postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    echo "database $DB_NAME already exists — leaving it alone"
    return 0
  fi
  echo "cloning $SOURCE_DB -> $DB_NAME"
  psql_pg postgres -c "CREATE DATABASE $DB_NAME OWNER dieselbridge;" >/dev/null
  # Dump/restore rather than CREATE DATABASE ... TEMPLATE: the template form
  # fails while anything is connected to the source, and the source is usually
  # another agent's live API. This never disturbs their connections.
  docker exec "$PG_CONTAINER" sh -c \
    "pg_dump -U dieselbridge -d $SOURCE_DB | psql -q -U dieselbridge -d $DB_NAME" >/dev/null
  echo "cloned."
}

cmd_up() {
  [ -f backend/.env ] || { echo "backend/.env missing (gitignored, not copied into worktrees)"; exit 1; }
  cmd_db_clone
  "${COMPOSE[@]}" up -d --build
  echo "migrating $DB_NAME to head"
  "${COMPOSE[@]}" exec -T api alembic upgrade head 2>&1 | tail -3
  echo
  echo "API  http://127.0.0.1:$API_PORT   (db: $DB_NAME, redis db $REDIS_DB)"
  echo "Web  DIESELBRIDGE_API_ORIGIN=http://127.0.0.1:$API_PORT npm run dev -- --port $WEB_PORT"
}

cmd_down() { "${COMPOSE[@]}" down; }
cmd_logs() { "${COMPOSE[@]}" logs -f api; }

# The awareness half: every API container on this machine, which worktree and
# branch it actually serves, and which database it is pointed at. Branch comes
# from the mounted source, not from a label, so it cannot drift.
cmd_status() {
  printf '%-26s %-7s %-34s %-24s %s\n' CONTAINER PORT WORKTREE BRANCH DATABASE
  docker ps --filter 'name=dieselbridge_api' --format '{{.Names}}' | sort | while read -r c; do
    port=$(docker port "$c" 2>/dev/null | head -1 | sed 's/.*://')
    src=$(docker inspect "$c" --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}')
    wt=$(dirname "$src" 2>/dev/null)
    br=$(git -C "$wt" branch --show-current 2>/dev/null || echo '?')
    dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    [ "${dirty:-0}" -gt 0 ] && br="$br (+$dirty)"
    db=$(docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' \
         | grep '^DATABASE_URL=' | sed 's#.*/##')
    printf '%-26s %-7s %-34s %-24s %s\n' "$c" "${port:-?}" "$(basename "$wt")" "$br" "$db"
  done
  echo
  printf '%-26s %s\n' 'VITE (host)' 'worktree'
  for p in $(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk '/node/ {split($9,a,":"); print a[2]}' | sort -u); do
    pid=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null | head -1)
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-)
    printf '%-26s %s\n' ":$p" "$(basename "$(dirname "$cwd")")"
  done
}

case "${1:-status}" in
  up) cmd_up ;;
  down) cmd_down ;;
  logs) cmd_logs ;;
  status) cmd_status ;;
  db-clone) cmd_db_clone ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
