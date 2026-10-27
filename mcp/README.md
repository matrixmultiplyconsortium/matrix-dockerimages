# Matrix Compute MCP Server Docker Image (`matrix-compute-mcp`)

Packages the official Model Context Protocol (MCP) server (`matrix-compute-mcp`) and high-level verifiable AI primitives (`matrix_compute_mcp.ai`) alongside `matrix-compute-sdk` and `matrix-contracts` into an isolated container.

## Features

- Multi-stage build producing a clean Python 3.11 runtime image.
- Runs as an unprivileged user (`matrixuser`, UID 1000).
- Exposes the `matrix-compute-mcp` stdio JSON-RPC 2.0 entrypoint for Claude Desktop, Cursor, Antigravity, LangChain, and OpenClaw.
- Supports `/app/data` volume mounting for `.npy`, `.npz`, and `.safetensors` tensor files.

## Build

From the root of the `DistributedMatrixMultiply` workspace:

```bash
docker build -f matrix-dockerimages/mcp/Dockerfile -t matrix-compute-mcp:latest .
```

## Running the Container

### View CLI Help
```bash
docker run --rm matrix-compute-mcp:latest --help
```

### MCP Client Configuration (Claude Desktop / Cursor / Antigravity via Docker)
```json
{
  "mcpServers": {
    "matrix-compute": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "/path/to/local/tensors:/app/data",
        "-e",
        "MATRIX_NOSTR_RELAYS",
        "-e",
        "MATRIX_SETTLEMENT_API_URL",
        "-e",
        "MATRIX_L402_MACAROON",
        "-e",
        "MATRIX_OFFLINE_MOCK_MODE",
        "matrix-compute-mcp:latest"
      ],
      "env": {
        "MATRIX_NOSTR_RELAYS": "ws://host.docker.internal:8008",
        "MATRIX_SETTLEMENT_API_URL": "http://host.docker.internal:8080",
        "MATRIX_L402_MACAROON": "",
        "MATRIX_OFFLINE_MOCK_MODE": "false"
      }
    }
  }
}
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `MATRIX_NOSTR_RELAYS` | Comma-separated Nostr discovery relay WebSocket URLs | `ws://localhost:8080` |
| `MATRIX_SETTLEMENT_API_URL` | Settlement HTTP API base URL | `http://localhost:8000` |
| `MATRIX_L402_MACAROON` | Optional L402 Macaroon token for authenticated settlement | *(unset)* |
| `MATRIX_TRIAL_API_KEY` | Optional trial API key for zero-setup agent onboarding | *(unset)* |
| `MATRIX_OFFLINE_MOCK_MODE` | Set to `true` for hermetic in-process mock relay & workers | `true` |
