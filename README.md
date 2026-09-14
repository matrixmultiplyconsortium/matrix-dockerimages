# Matrix Docker Images (`matrix-dockerimages`)

Container definitions, Dockerfiles, and orchestration configurations for the **Distributed Matrix Multiplication** network.

This repository packages the four core architectural components into isolated, production-ready container images:

| Component | Directory | Description | Default Port |
|---|---|---|---|
| **Client** | [`client/`](./client/) | Consumer SDK orchestrator (`matrix-compute-sdk`) for matrix slicing, task dispatch, and Freivalds verification | N/A (CLI) |
| **Compute Node** | [`compute-node/`](./compute-node/) | Decentralized worker daemon (`matrix-compute-node`) for hardware attestation and tensor ops | `50051` (gRPC) |
| **Relay** | [`relay/`](./relay/) | Nostr Kind 30000 worker registry and matchmaking service (`matrix-compute-relay`) | `8008` (WebSocket) |
| **Settlement** | [`settlement/`](./settlement/) | Lightning L402 invoice manager and economic routing layer (`matrix-compute-settlement`) | `8080` (HTTP) |

---

## Repository Structure

```
matrix-dockerimages/
├── .gitignore               # Build cache and environment ignores
├── .env.example             # Configuration variables template
├── docker-compose.yml       # Local multi-service cluster orchestration
├── README.md                # Repository documentation
├── client/
│   ├── Dockerfile           # Multi-stage Python 3.11 build for consumer client
│   ├── .dockerignore
│   └── README.md
├── compute-node/
│   ├── Dockerfile           # Standard CPU worker node image
│   ├── Dockerfile.gpu       # NVIDIA CUDA 12.x worker image with GPU passthrough
│   ├── .dockerignore
│   └── README.md
├── relay/
│   ├── Dockerfile           # Discovery relay image
│   ├── .dockerignore
│   └── README.md
└── settlement/
    ├── Dockerfile           # Settlement layer image
    ├── .dockerignore
    └── README.md
```

---

## Quickstart with Docker Compose

From the root of the `DistributedMatrixMultiply` workspace, start the core cluster services (`relay`, `settlement`, and `compute-node`):

```bash
# Start background services
docker compose -f matrix-dockerimages/docker-compose.yml up -d relay settlement compute-node

# View service logs
docker compose -f matrix-dockerimages/docker-compose.yml logs -f

# Run the client orchestrator container
docker compose -f matrix-dockerimages/docker-compose.yml run --rm client --help
```

To tear down the network:

```bash
docker compose -f matrix-dockerimages/docker-compose.yml down
```

---

## Individual Image Builds

Each container image can be built independently from the `DistributedMatrixMultiply` workspace root:

### 1. Client
```bash
docker build -f matrix-dockerimages/client/Dockerfile -t matrix-client:latest .
```

### 2. Compute Node (CPU)
```bash
docker build -f matrix-dockerimages/compute-node/Dockerfile -t matrix-compute-node:latest .
```

### 3. Compute Node (GPU / CUDA)
```bash
docker build -f matrix-dockerimages/compute-node/Dockerfile.gpu -t matrix-compute-node:gpu .
```

### 4. Discovery Relay
```bash
docker build -f matrix-dockerimages/relay/Dockerfile -t matrix-relay:latest .
```

### 5. Settlement Layer
```bash
docker build -f matrix-dockerimages/settlement/Dockerfile -t matrix-settlement:latest .
```

---

## Network Architecture & Ports

```
                 +-----------------------+
                 | Discovery Relay       |
                 | (WebSocket port 8008) |
                 +-----------+-----------+
                             ^
                             | (Kind 30000 Announce & Query)
+-----------------------+    |    +-----------------------+
| Consumer Client       +----+----+ Worker Compute Node   |
| (matrix-compute-sdk)  |         | (gRPC port 50051)     |
+-----------+-----------+         +-----------+-----------+
            |                                 |
            | (L402 Payment & Verification)   |
            v                                 v
         +---------------------------------------+
         | Settlement Layer                      |
         | (HTTP port 8080)                      |
         +---------------------------------------+
```

---

## Development & Roadmap Notes

- **Relay**: Discovery Relay server milestones are actively in progress. The relay image builds from the current `matrix-compute-relay` package.
- **Settlement**: The settlement service implementation is in progress. The settlement container is scaffolded with standard runtime dependencies ready for integration.
- **Registry Publishing**: Images are currently targeted for local builds and development clusters. Registry CI/CD workflows will be introduced when production deployment pipelines are activated.
