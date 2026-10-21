#!/usr/bin/env bash
set -e

# Optional Tailscale bootstrap for cloud GPU rentals (Vast.ai / RunPod)
# If TAILSCALE_AUTHKEY is provided, starts tailscaled and joins the tailnet.
if [ -n "${TAILSCALE_AUTHKEY:-}" ]; then
    echo "[entrypoint] Starting tailscaled..."
    mkdir -p /var/run/tailscale /var/cache/tailscale /var/lib/tailscale
    if [ -e /dev/net/tun ] && capsh --print 2>/dev/null | grep -q "cap_net_admin"; then
        tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock &
    else
        echo "[entrypoint] /dev/net/tun unavailable or unprivileged; using userspace-networking mode"
        tailscaled --tun=userspace-networking --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock &
    fi
    sleep 2
    TS_HOSTNAME="${TAILSCALE_HOSTNAME:-matrix-gpu-worker}"
    tailscale --socket=/var/run/tailscale/tailscaled.sock up \
        --authkey="${TAILSCALE_AUTHKEY}" \
        --hostname="${TS_HOSTNAME}" \
        --accept-routes
    TS_IP=$(tailscale --socket=/var/run/tailscale/tailscaled.sock ip -4 | head -n 1 || true)
    if [ -n "${TS_IP}" ] && [ -z "${MATRIX_WORKER_P2P_MULTIADDR:-}" ]; then
        P2P_PORT="${MATRIX_WORKER_P2P_PORT:-50051}"
        export MATRIX_WORKER_P2P_MULTIADDR="/ip4/${TS_IP}/tcp/${P2P_PORT}"
        echo "[entrypoint] Tailscale connected: advertising ${MATRIX_WORKER_P2P_MULTIADDR}"
    fi
fi

# If first argument looks like a flag (e.g. --inject-fraud) or no args are given,
# invoke matrix-compute-node directly. Otherwise execute the passed command
# (allows Vast.ai / RunPod custom wrapper commands if needed).
if [ $# -eq 0 ] || [ "${1#-}" != "$1" ]; then
    exec matrix-compute-node "$@"
else
    exec "$@"
fi
