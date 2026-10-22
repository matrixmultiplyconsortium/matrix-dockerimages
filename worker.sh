#!/usr/bin/env bash
# ==============================================================================
# Distributed Matrix Multiply — 1-Click Worker Node Installer (Linux / macOS)
#
# Auto-detects compute hardware (NVIDIA GPU, AMD ROCm, AMD SEV-SNP, Intel TDX, CPU),
# verifies container runtime, configures worker Nostr keypair, enables zero-config
# outbound-only NAT traversal, and renders the operator dashboard with Lightning QR.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATRIX_DIR="${HOME}/.matrix"
ENV_FILE="${MATRIX_DIR}/worker.env"

# Default configuration values
PAYOUT_ADDRESS=""
NOSTR_RELAYS="wss://relay.matrixcompute.io"
SETTLEMENT_API_URL="http://settlement.matrixcompute.io:8000"
SATS_PER_GFLOP="1.0"
MIN_TASK_SATS="1"
NAT_MODE="reverse_tunnel"
DRY_RUN=false
MOCK_HARDWARE=""
NON_INTERACTIVE=false

# ANSI color formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

log_info() {
    printf "${CYAN}[*] %s${RESET}\n" "$1"
}

log_success() {
    printf "${GREEN}[+] %s${RESET}\n" "$1"
}

log_warn() {
    printf "${YELLOW}[!] %s${RESET}\n" "$1"
}

log_error() {
    printf "${RED}[-] %s${RESET}\n" "$1" >&2
}

# Parse command line flags
while [ $# -gt 0 ]; do
    case "$1" in
        --payout-address|-p)
            PAYOUT_ADDRESS="$2"
            shift 2
            ;;
        --relays|-r)
            NOSTR_RELAYS="$2"
            shift 2
            ;;
        --settlement-url|-s)
            SETTLEMENT_API_URL="$2"
            shift 2
            ;;
        --sats-per-gflop)
            SATS_PER_GFLOP="$2"
            shift 2
            ;;
        --min-task-sats)
            MIN_TASK_SATS="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --mock-hardware)
            MOCK_HARDWARE="$2"
            shift 2
            ;;
        --non-interactive|-y)
            NON_INTERACTIVE=true
            shift
            ;;
        --help|-h)
            printf "Usage: %s [OPTIONS]\n" "$0"
            printf "Options:\n"
            printf "  -p, --payout-address <addr>   Lightning Address or LNURL for earnings payout\n"
            printf "  -r, --relays <urls>           Comma-separated Nostr relay endpoints\n"
            printf "  -s, --settlement-url <url>    Settlement coordination API URL\n"
            printf "      --sats-per-gflop <val>    Price quote per GFLOP computed (default: 1.0)\n"
            printf "      --min-task-sats <val>     Minimum job payout accepted (default: 1)\n"
            printf "      --env-file <path>         Target worker environment file (default: ~/.matrix/worker.env)\n"
            printf "      --dry-run                 Simulate checks and print configuration without starting container\n"
            printf "      --mock-hardware <profile> Simulate hardware: nvidia, rocm, sev-snp, tdx, cpu\n"
            printf "  -y, --non-interactive         Skip interactive configuration prompts\n"
            printf "  -h, --help                    Display this help message\n"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

printf "\n${BOLD}${CYAN}=== Distributed Matrix Multiply — Worker Bootstrap ===${RESET}\n\n"

# 1. Verify Python 3
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    log_error "Python 3.8+ is required for worker onboarding tooling."
    exit 1
fi
log_success "Python runtime verified: $("$PYTHON_BIN" --version 2>&1)"

# 2. Check Docker Runtime
DOCKER_BIN=""
if command -v docker >/dev/null 2>&1; then
    DOCKER_BIN="docker"
fi

if [ -z "$DOCKER_BIN" ]; then
    if [ "$DRY_RUN" = true ]; then
        log_warn "Docker not detected on host (skipped in --dry-run mode)"
    else
        log_error "Docker is not installed. Please install Docker Engine: https://docs.docker.com/engine/install/"
        exit 1
    fi
else
    log_success "Docker CLI detected: $("$DOCKER_BIN" --version 2>&1)"
    if [ "$DRY_RUN" = false ]; then
        if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
            log_error "Docker daemon is not running or current user lacks docker group permissions."
            exit 1
        fi
        log_success "Docker daemon connectivity confirmed"
    fi
fi

# 3. Hardware & TEE Detection Cascade
log_info "Probing system compute capabilities & enclaves..."
PROBE_CMD=("$PYTHON_BIN" -m scripts.onboard probe)
if [ -n "$MOCK_HARDWARE" ]; then
    PROBE_CMD+=(--mock "$MOCK_HARDWARE")
fi

PROBE_OUTPUT=$(cd "$SCRIPT_DIR" && "${PROBE_CMD[@]}")
IS_GPU=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(str(d.get('is_gpu', False)).lower())" "$PROBE_OUTPUT")
IS_TEE=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(str(d.get('is_tee', False)).lower())" "$PROBE_OUTPUT")
HW_VENDOR=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('vendor', 'Unknown'))" "$PROBE_OUTPUT")
HW_MODEL=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('model', 'Unknown'))" "$PROBE_OUTPUT")
HW_TFLOPS=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('tflops', 0.0))" "$PROBE_OUTPUT")
TEE_TYPE=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('tee_type') or 'None')" "$PROBE_OUTPUT")

log_success "Detected Hardware: ${HW_MODEL} (${HW_VENDOR}) — ${HW_TFLOPS} TFLOPS FP32"
if [ "$IS_TEE" = "true" ]; then
    log_success "Confidential Computing Enclave: ${TEE_TYPE}"
fi

# 4. Identity & Configuration File
if [ -f "$ENV_FILE" ]; then
    log_info "Existing worker configuration found at $ENV_FILE"
    WORKER_PRIVKEY=$(grep -E "^MATRIX_WORKER_PRIVKEY=" "$ENV_FILE" | cut -d= -f2- || true)
    WORKER_NPUB=$(grep -E "^MATRIX_WORKER_NPUB=" "$ENV_FILE" | cut -d= -f2- || true)
    WORKER_NSEC=$(grep -E "^MATRIX_WORKER_NSEC=" "$ENV_FILE" | cut -d= -f2- || true)
    SAVED_PAYOUT=$(grep -E "^MATRIX_WORKER_PAYOUT_ADDRESS=" "$ENV_FILE" | cut -d= -f2- || true)
    if [ -z "$PAYOUT_ADDRESS" ] && [ -n "$SAVED_PAYOUT" ]; then
        PAYOUT_ADDRESS="$SAVED_PAYOUT"
    fi
else
    log_info "Generating new worker Nostr Secp256k1 identity..."
    KEYGEN_CMD=("$PYTHON_BIN" -m scripts.onboard keygen --output "$ENV_FILE")
    if [ -n "$PAYOUT_ADDRESS" ]; then
        KEYGEN_CMD+=(--payout-address "$PAYOUT_ADDRESS")
    fi
    KEYGEN_OUTPUT=$(cd "$SCRIPT_DIR" && "${KEYGEN_CMD[@]}")
    WORKER_PRIVKEY=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('hex_privkey'))" "$KEYGEN_OUTPUT")
    WORKER_NPUB=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('npub'))" "$KEYGEN_OUTPUT")
    WORKER_NSEC=$("$PYTHON_BIN" -c "import json, sys; d=json.loads(sys.argv[1]); print(d.get('nsec'))" "$KEYGEN_OUTPUT")
    log_success "Created worker identity: ${WORKER_NPUB}"
fi

# Fallback payout prompt if interactive and not provided
if [ -z "$PAYOUT_ADDRESS" ] && [ "$NON_INTERACTIVE" = false ] && [ -t 0 ]; then
    printf "${BOLD}Enter Lightning Address or LNURL for earnings payout (or press Enter to skip): ${RESET}"
    read -r user_payout || true
    if [ -n "$user_payout" ]; then
        PAYOUT_ADDRESS="$user_payout"
    fi
fi
if [ -z "$PAYOUT_ADDRESS" ]; then
    PAYOUT_ADDRESS="worker@matrixcompute.io"
fi

# 5. Determine Docker Container Specification
if [ "$IS_GPU" = "true" ]; then
    CONTAINER_IMAGE="matrixcompute/worker:gpu"
    if [ "$HW_VENDOR" = "NVIDIA" ]; then
        GPU_FLAGS="--gpus all --ipc=host"
    else
        # AMD ROCm flags
        GPU_FLAGS="--device=/dev/kfd --device=/dev/dri --ipc=host"
    fi
else
    CONTAINER_IMAGE="matrixcompute/worker:latest"
    GPU_FLAGS=""
fi

TEE_FLAGS=""
if [ "$TEE_TYPE" = "AMD_SEV_SNP" ]; then
    TEE_FLAGS="--device=/dev/sev-guest"
elif [ "$TEE_TYPE" = "INTEL_TDX" ]; then
    TEE_FLAGS="--device=/dev/tdx_guest"
fi

DOCKER_RUN_CMD="docker run -d \
  --name matrix-worker \
  --restart unless-stopped \
  --network host \
  ${GPU_FLAGS} \
  ${TEE_FLAGS} \
  -e MATRIX_WORKER_PRIVKEY=\"${WORKER_PRIVKEY}\" \
  -e MATRIX_WORKER_NPUB=\"${WORKER_NPUB}\" \
  -e MATRIX_WORKER_PAYOUT_ADDRESS=\"${PAYOUT_ADDRESS}\" \
  -e MATRIX_WORKER_NOSTR_RELAYS=\"${NOSTR_RELAYS}\" \
  -e MATRIX_WORKER_SETTLEMENT_API_URL=\"${SETTLEMENT_API_URL}\" \
  -e MATRIX_WORKER_SATS_PER_GFLOP=\"${SATS_PER_GFLOP}\" \
  -e MATRIX_WORKER_MIN_TASK_SATS=\"${MIN_TASK_SATS}\" \
  -e MATRIX_WORKER_NAT_MODE=\"${NAT_MODE}\" \
  ${CONTAINER_IMAGE}"

# 6. Execute or Simulate Run
if [ "$DRY_RUN" = true ]; then
    log_info "Dry-Run Active. Generated Docker Execution Command:"
    printf "\n${YELLOW}%s${RESET}\n\n" "$DOCKER_RUN_CMD"
else
    log_info "Launching compute worker container..."
    # If container with same name exists, stop/remove
    if "$DOCKER_BIN" ps -a --format '{{.Names}}' | grep -Eq "^matrix-worker$"; then
        log_info "Replacing existing matrix-worker container..."
        "$DOCKER_BIN" rm -f matrix-worker >/dev/null 2>&1 || true
    fi
    eval "$DOCKER_RUN_CMD" >/dev/null
    log_success "Worker container started successfully (ID: $(docker ps -q -f name=matrix-worker))"
fi

# 7. Render Operator Dashboard
DASH_CMD=("$PYTHON_BIN" -m scripts.onboard dashboard --payout "$PAYOUT_ADDRESS" --npub "$WORKER_NPUB" --nat-mode "OUTBOUND-ONLY NAT" --tier "PROBATIONARY")
if [ -n "$MOCK_HARDWARE" ]; then
    DASH_CMD+=(--mock "$MOCK_HARDWARE")
fi

printf "\n"
(cd "$SCRIPT_DIR" && "${DASH_CMD[@]}")
printf "\n${GREEN}[✓] Setup complete! Worker is connected and listening for matrix tile jobs via outbound reverse tunnel.${RESET}\n\n"
