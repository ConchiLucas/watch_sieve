#!/usr/bin/env bash
# Start or stop the WatchSieve web UI and SnailJob executor together.
# Reuses already-running processes (by pid file, listen port, or command line).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BIN="$ROOT/.venv/bin"
LOG="$ROOT/log"
mkdir -p "$LOG"

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/.playwright-browsers}"

WEB_PORT=8000
SNAIL_HOST_PORT=17889
if [[ -f "$ROOT/.env" ]]; then
  env_port="$(grep -E '^SNAIL_HOST_PORT=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
  if [[ "$env_port" =~ ^[0-9]+$ ]]; then
    SNAIL_HOST_PORT="$env_port"
  fi
fi

usage() {
  echo "Usage: $0 [start|stop|status]"
}

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

listener_pid() {
  local port="$1"
  local pid
  pid="$(lsof -nP "-iTCP:${port}" -sTCP:LISTEN -t 2>/dev/null | awk 'NR==1')" || true
  [[ -n "$pid" ]] && echo "$pid"
}

cmdline_pid() {
  local pattern="$1"
  local pid
  pid="$(pgrep -f "$pattern" 2>/dev/null | awk -v self="$$" -v parent="$PPID" '$1 != self && $1 != parent { print; exit }')" || true
  [[ -n "$pid" ]] && echo "$pid"
}

find_web_pid() {
  local pid=""
  if [[ -f "$LOG/web.pid" ]]; then
    pid="$(cat "$LOG/web.pid")"
    if pid_alive "$pid"; then
      echo "$pid"
      return 0
    fi
  fi
  pid="$(listener_pid "$WEB_PORT")"
  if pid_alive "$pid"; then
    echo "$pid"
    return 0
  fi
  cmdline_pid '[w]atch-sieve-web|[w]atch_sieve.server' || true
  return 0
}

find_snailjob_pid() {
  local pid=""
  if [[ -f "$LOG/snailjob.pid" ]]; then
    pid="$(cat "$LOG/snailjob.pid")"
    if pid_alive "$pid"; then
      echo "$pid"
      return 0
    fi
  fi
  pid="$(listener_pid "$SNAIL_HOST_PORT")"
  if pid_alive "$pid"; then
    echo "$pid"
    return 0
  fi
  cmdline_pid '[w]atch-sieve-snailjob|[s]nailjob_worker' || true
  return 0
}

remember_pid() {
  local name="$1"
  local pid="$2"
  echo "$pid" >"$LOG/$name.pid"
}

start_one() {
  local name="$1"
  local cmd="$2"
  local finder="$3"
  local pidfile="$LOG/$name.pid"
  local logfile="$LOG/$name.log"
  local pid
  pid="$($finder)"
  if pid_alive "$pid"; then
    remember_pid "$name" "$pid"
    echo "$name already running (pid $pid), skip"
    return
  fi
  "$BIN/python" - "$ROOT" "$cmd" "$logfile" "$pidfile" <<'PY'
import os
import sys

root, command, logfile, pidfile = sys.argv[1:5]
os.chdir(root)
if os.fork() > 0:
    sys.exit(0)
os.setsid()
if os.fork() > 0:
    sys.exit(0)
os.umask(0)
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)
os.close(devnull)
logfd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(logfd, 1)
os.dup2(logfd, 2)
if logfd not in (1, 2):
    os.close(logfd)
with open(pidfile, "w", encoding="utf-8") as handle:
    handle.write(str(os.getpid()))
os.execv(command, [command])
PY
  sleep 0.3
  pid="$($finder)"
  if pid_alive "$pid"; then
    remember_pid "$name" "$pid"
    echo "started $name (pid $pid)"
  else
    echo "failed to start $name; see $logfile"
    return 1
  fi
}

stop_one() {
  local name="$1"
  local finder="$2"
  local pid
  pid="$($finder)"
  if ! pid_alive "$pid"; then
    rm -f "$LOG/$name.pid"
    echo "$name not running"
    return
  fi
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pid_alive "$pid" || break
    sleep 0.2
  done
  if pid_alive "$pid"; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$LOG/$name.pid"
  echo "stopped $name (pid $pid)"
}

status_one() {
  local name="$1"
  local finder="$2"
  local pid
  pid="$($finder)"
  if pid_alive "$pid"; then
    remember_pid "$name" "$pid"
    echo "$name running (pid $pid)"
  else
    rm -f "$LOG/$name.pid"
    echo "$name stopped"
  fi
}

require_venv() {
  if [[ ! -x "$BIN/watch-sieve-web" || ! -x "$BIN/watch-sieve-snailjob" ]]; then
    echo "Missing venv commands. From the repo root run: python -m venv .venv && .venv/bin/pip install -e \".[dev,snailjob]\""
    exit 1
  fi
}

cmd="${1:-start}"
case "$cmd" in
  start)
    require_venv
    start_one web "$BIN/watch-sieve-web" find_web_pid
    start_one snailjob "$BIN/watch-sieve-snailjob" find_snailjob_pid
    echo "web http://127.0.0.1:${WEB_PORT}"
    echo "logs $LOG/web.log $LOG/snailjob.log"
    echo "SnailJob admin is Docker, not this script: http://127.0.0.1:18080/snail-job"
    ;;
  stop)
    stop_one web find_web_pid
    stop_one snailjob find_snailjob_pid
    ;;
  status)
    status_one web find_web_pid
    status_one snailjob find_snailjob_pid
    ;;
  *)
    usage
    exit 1
    ;;
esac
