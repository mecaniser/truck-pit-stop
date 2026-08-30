#!/usr/bin/env bash
# Reap dev containers that are still running but nobody is using.
#
# Per-ticket QA stacks get created and never torn down, so the machine ends up
# running a dozen idle Postgres and Redis instances from work that shipped weeks
# ago. Each holds memory inside the Docker VM and a host port.
#
# Lifetime is measured by observed traffic, not by branch state. Branch state
# was tried and does not work here: db038 still had three unmerged branches
# after it shipped, and the open PR for db046 sits on a branch whose name never
# mentions the ticket. Either signal would have protected exactly the
# containers that needed reaping. Traffic cannot lie: a database nothing has
# talked to in a working day is not in use.
#
# Dry run by default. Volumes are never removed unless --prune-volumes is given.
set -euo pipefail

KEEP="${DOCKER_REAP_KEEP:-dieselbridge_postgres dieselbridge_redis dieselbridge_api_dev}"
MIN_AGE_HOURS="${DOCKER_REAP_MIN_AGE_HOURS:-24}"
SAMPLE_SECONDS="${DOCKER_REAP_SAMPLE_SECONDS:-5}"
APPLY=0
PRUNE_VOLUMES=0

usage() {
  cat <<'USAGE'
usage: docker-reap.sh [--apply] [--min-age-hours N] [--sample-seconds N]
                      [--keep "a b"] [--prune-volumes]

  --apply            stop and remove the idle containers (default: list only)
  --min-age-hours N  never touch anything younger than this (default 24)
  --sample-seconds N seconds between traffic samples (default 5)
  --keep "a b"       names to protect regardless of activity
  --prune-volumes    also prune dangling volumes afterwards (destroys data)
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --min-age-hours) MIN_AGE_HOURS="$2"; shift 2 ;;
    --sample-seconds) SAMPLE_SECONDS="$2"; shift 2 ;;
    --keep) KEEP="$2"; shift 2 ;;
    --prune-volumes) PRUNE_VOLUMES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

docker info >/dev/null 2>&1 || { echo "docker is not running; nothing to do"; exit 0; }

is_kept() { for k in $KEEP; do [ "$1" = "$k" ] && return 0; done; return 1; }

age_hours() {
  local started epoch now
  started=$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null) || return 1
  epoch=$(date -j -u -f "%Y-%m-%dT%H:%M:%S" "${started%.*}" +%s 2>/dev/null \
    || date -u -d "$started" +%s 2>/dev/null) || return 1
  now=$(date +%s)
  echo $(( (now - epoch) / 3600 ))
}

# Exact cumulative network bytes per container, straight from the daemon.
# docker stats was tried first and is unusable here: it rounds to three
# significant figures, so five HTTP requests against a container sitting at
# "10.3GB" move nothing on screen and the container reads as idle.
sample_io() {
  docker ps --format '{{.Names}}' | while read -r n; do
    [ -n "$n" ] || continue
    bytes=$(curl -s --unix-socket /var/run/docker.sock \
      "http://localhost/containers/$n/stats?stream=false" 2>/dev/null \
      | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(0); raise SystemExit
nets = d.get('networks') or {}
print(sum(v.get('rx_bytes', 0) + v.get('tx_bytes', 0) for v in nets.values()))
" 2>/dev/null)
    echo "$n ${bytes:-0}"
  done
}

STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/docker-reap"
STATE="$STATE_DIR/baseline"
mkdir -p "$STATE_DIR"

now_epoch=$(date +%s)
current=$(sample_io)

if [ ! -s "$STATE" ]; then
  printf '%s\n' "$current" | while read -r n rest; do echo "$n|$rest|$now_epoch"; done > "$STATE"
  echo "baseline recorded for $(wc -l < "$STATE" | tr -d ' ') container(s)."
  echo "run again after ${MIN_AGE_HOURS}h and anything whose counters have not moved is idle."
  exit 0
fi

idle=() ; active=() ; young=()
while IFS= read -r name; do
  [ -n "$name" ] || continue
  is_kept "$name" && continue
  hours=$(age_hours "$name" 2>/dev/null || echo 0)
  if [ "$hours" -lt "$MIN_AGE_HOURS" ]; then
    young+=("$name (${hours}h)")
    continue
  fi
  cur=$(printf '%s\n' "$current" | awk -v n="$name" '$1==n {print $2}')
  line=$(grep -m1 "^${name}|" "$STATE" 2>/dev/null || true)
  if [ -z "$line" ]; then
    young+=("$name (no baseline yet)")
    continue
  fi
  was=${line#*|}; was=${was%|*}
  since=${line##*|}
  elapsed_h=$(( (now_epoch - since) / 3600 ))
  if [ "$elapsed_h" -lt "$MIN_AGE_HOURS" ]; then
    young+=("$name (only ${elapsed_h}h since baseline)")
  elif [ "$(echo $was)" = "$(echo $cur)" ]; then
    idle+=("$name|${elapsed_h}h idle")
  else
    active+=("$name (traffic since baseline)")
  fi
done < <(docker ps --format '{{.Names}}')

[ "${#active[@]}" -gt 0 ] && { echo; echo "In use (traffic moved during the sample):"; printf '  %s\n' "${active[@]}"; }
[ "${#young[@]}"  -gt 0 ] && { echo; echo "Too new to judge (< ${MIN_AGE_HOURS}h):";   printf '  %s\n' "${young[@]}"; }

if [ "${#idle[@]}" -eq 0 ]; then
  echo; echo "nothing idle to reap (protected: $KEEP)"
  exit 0
fi

echo; echo "No traffic since the baseline, and older than ${MIN_AGE_HOURS}h:"
for e in "${idle[@]}"; do printf '  %-30s %s\n' "${e%%|*}" "${e##*|}"; done

if [ "$APPLY" -ne 1 ]; then
  echo; echo "dry run — re-run with --apply to stop and remove these"
  exit 0
fi

names=(); for e in "${idle[@]}"; do names+=("${e%%|*}"); done
printf '%s\n' "${names[@]}" | xargs docker stop >/dev/null
printf '%s\n' "${names[@]}" | xargs docker rm >/dev/null
printf '%s\n' "$(sample_io)" | while read -r n rest; do echo "$n|$rest|$now_epoch"; done > "$STATE"
echo; echo "removed ${#names[@]} container(s); baseline reset"

if [ "$PRUNE_VOLUMES" -eq 1 ]; then
  echo "pruning dangling volumes..."
  docker volume prune -f | tail -1
else
  dangling=$(docker volume ls -qf dangling=true | wc -l | tr -d ' ')
  [ "$dangling" -gt 0 ] && echo "$dangling dangling volume(s) left in place; --prune-volumes removes them"
fi
