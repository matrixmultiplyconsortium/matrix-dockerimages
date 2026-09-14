# Matrix Discovery Relay Docker Image

Packages the `matrix-compute-relay` service for managing Nostr Kind 30000 worker registrations and Pareto matchmaking queries.

## Features

- Multi-stage build producing a lightweight Python 3.11 image.
- Runs as an unprivileged user (`relayuser`, UID 1000).
- Exposes WebSocket port `8008` for Nostr discovery events.

## Build

From the root of the `DistributedMatrixMultiply` workspace:

```bash
docker build -f matrix-dockerimages/relay/Dockerfile -t matrix-relay:latest .
```

## Running the Relay

```bash
docker run -d \
  --name matrix-relay \
  -p 8008:8008 \
  -e MATRIX_RELAY_HOST="0.0.0.0" \
  -e MATRIX_RELAY_PORT=8008 \
  matrix-relay:latest
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MATRIX_RELAY_HOST` | Host interface to bind WebSocket server | `0.0.0.0` |
| `MATRIX_RELAY_PORT` | Port for incoming Nostr WebSocket traffic | `8008` |
| `MATRIX_RELAY_PUBKEY` | 32-byte hex public key identity of the relay | `0000...0000` |
| `MATRIX_RELAY_DEFAULT_TTL_SECONDS` | TTL for worker announcements in seconds | `3600` |
| `MATRIX_RELAY_MAX_EVENTS` | Maximum capacity for in-memory event registry | `10000` |
| `MATRIX_RELAY_MIN_STAKED_SATS` | Minimum required worker bond in satoshis | `0` |
| `MATRIX_RELAY_LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) | `INFO` |

*Note: Discovery Relay implementation is ongoing. The Dockerfile builds cleanly from the current package definition.*
