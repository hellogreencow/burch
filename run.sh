#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"
AUTO_OPEN_PID=""

ensure_env_file() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "[run] Created .env from .env.example"
  fi

  if grep -q '^OPENROUTER_API_KEY=' .env; then
    current_key="$(grep '^OPENROUTER_API_KEY=' .env | cut -d= -f2- || true)"
    if [[ -z "${current_key}" ]]; then
      if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
        sed -i.bak "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=${OPENROUTER_API_KEY}|" .env
        rm -f .env.bak
        echo "[run] Set OPENROUTER_API_KEY from environment variable"
      else
        echo "[run] OPENROUTER_API_KEY is empty in .env (AI chat will use fallback mode)."
      fi
    fi
  else
    if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
      printf "\nOPENROUTER_API_KEY=%s\n" "${OPENROUTER_API_KEY}" >> .env
      echo "[run] Added OPENROUTER_API_KEY from environment variable"
    else
      printf "\nOPENROUTER_API_KEY=\n" >> .env
      echo "[run] Added empty OPENROUTER_API_KEY to .env (fallback chat mode)."
    fi
  fi
}

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

pick_random_free_port() {
  local avoid="${1:-}"
  local candidate

  while true; do
    candidate=$(( (RANDOM % 30000) + 20000 ))
    if [[ -n "${avoid}" && "${candidate}" == "${avoid}" ]]; then
      continue
    fi
    if ! port_in_use "${candidate}"; then
      echo "${candidate}"
      return 0
    fi
  done
}

setup_runtime_ports() {
  HOST_API_PORT="$(pick_random_free_port)"
  HOST_WEB_PORT="$(pick_random_free_port "${HOST_API_PORT}")"

  export HOST_API_PORT
  export HOST_WEB_PORT
  export CORS_ORIGIN="http://localhost:${HOST_WEB_PORT}"
  export NEXT_PUBLIC_API_BASE_URL=""
}

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  fi
}

auto_open_web_when_ready() {
  (
    local url="http://localhost:${HOST_WEB_PORT}"
    for _ in $(seq 1 120); do
      if curl -fsS "${url}" >/dev/null 2>&1; then
        open_url "${url}"
        echo "[run] Browser opened: ${url}"
        exit 0
      fi
      sleep 1
    done
    echo "[run] Auto-open skipped (web not ready in time)."
  ) &
  AUTO_OPEN_PID="$!"
}

shutdown_stack() {
  echo
  echo "[run] Stopping BURCH-EIDOLON..."
  if [[ -n "${AUTO_OPEN_PID}" ]] && kill -0 "${AUTO_OPEN_PID}" >/dev/null 2>&1; then
    kill "${AUTO_OPEN_PID}" >/dev/null 2>&1 || true
  fi
  docker compose down --remove-orphans || true
  echo "[run] Stopped."
}

trap 'shutdown_stack; exit 0' INT TERM

ensure_env_file
setup_runtime_ports
mkdir -p reports/generated

if ! docker info >/dev/null 2>&1; then
  echo "[run] Docker does not seem to be running."
  echo "[run] Start Docker Desktop (or your Docker daemon) and re-run: ./run.sh"
  exit 1
fi

echo "[run] Starting BURCH-EIDOLON..."
echo "[run] API port: ${HOST_API_PORT}"
echo "[run] Web port: ${HOST_WEB_PORT}"
echo "[run] Web: http://localhost:${HOST_WEB_PORT}"
echo "[run] API: http://localhost:${HOST_API_PORT}/docs"
echo "[run] Press Ctrl+C to stop all services."

auto_open_web_when_ready
docker compose up --build --remove-orphans
status=$?

shutdown_stack
exit "${status}"
