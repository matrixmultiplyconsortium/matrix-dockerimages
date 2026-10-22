#!/usr/bin/env bash
# ==============================================================================
# HiveOS Custom Miner Execution Script
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${CUSTOM_CONFIG_FILENAME:-/hive/miners/custom/matrix-worker/worker.conf}"
LOG_FILE="${CUSTOM_LOG_BASENAME:-/var/log/miner/custom/matrix-worker}.log"

mkdir -p "$(dirname "$LOG_FILE")"

if [ -f "$CONFIG_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
    set +a
fi

echo "[*] Starting Distributed Matrix Multiply Worker under HiveOS..." | tee -a "$LOG_FILE"

# If docker is available, run container; otherwise run local python daemon
if command -v docker >/dev/null 2>&1; then
    docker run --rm \
      --name matrix-worker \
      --network host \
      --gpus all --ipc=host \
      --env-file "$CONFIG_FILE" \
      matrixcompute/worker:gpu >> "$LOG_FILE" 2>&1
else
    # Fallback to local python worker if container runtime is unavailable
    python3 -m src.main >> "$LOG_FILE" 2>&1
fi
