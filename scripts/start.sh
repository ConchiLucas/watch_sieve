#!/usr/bin/env bash
# One owner for both services: Docker Compose.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
compose() { docker compose -f "$ROOT/docker-compose.yml" "$@"; }
case "${1:-start}" in
  start) compose up -d --wait --wait-timeout 180 ;;
  stop) compose stop ;;
  restart) compose restart ;;
  status) compose ps -a ;;
  logs) compose logs --tail=100 -f ;;
  build) compose build ;;
  *) echo "Usage: $0 [start|stop|restart|status|logs|build]" >&2; exit 2 ;;
esac
