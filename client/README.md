# Matrix Consumer Client Docker Image

Packages the `matrix-compute-sdk` orchestrator into a container for running distributed matrix multiplication jobs.

## Features

- Multi-stage build producing a lightweight Python 3.11 image.
- Runs as an unprivileged user (`matrixuser`, UID 1000).
- Includes the `matrix-compute` CLI entrypoint.
- Supports volume mounting for matrix dataset input/output files.

## Build

From the root of the `DistributedMatrixMultiply` workspace:

```bash
docker build -f matrix-dockerimages/client/Dockerfile -t matrix-client:latest .
```

## Running the Container

### View CLI Help
```bash
docker run --rm matrix-client:latest --help
```

### Run with Local Volume for Data
```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  --network matrix-net \
  matrix-client:latest \
  --help
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MATRIX_CLIENT_RELAYS` | JSON array of Nostr discovery relay WebSocket URLs | `["ws://127.0.0.1:8008"]` |
| `MATRIX_CLIENT_SETTLEMENT_URL` | Settlement HTTP API base URL | `http://127.0.0.1:8080` |
| `MATRIX_CLIENT_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `OFFLINE_HERMETIC` | Set to `1` to run with offline hermetic test doubles | `0` |
