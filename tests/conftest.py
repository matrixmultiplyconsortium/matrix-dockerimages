"""
Pytest configuration, fixtures, and mocks for matrix-dockerimages test suite.
"""

import os
import sys
import tempfile
from typing import Generator
import pytest

# Ensure matrix-dockerimages is in sys.path
SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


@pytest.fixture
def tmp_worker_dir() -> Generator[str, None, None]:
    """Provides an isolated temporary directory for worker files."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def clean_matrix_env() -> Generator[None, None, None]:
    """Ensures test environment isolation by cleaning MATRIX_* environment variables."""
    old_env = os.environ.copy()
    keys_to_remove = [k for k in os.environ if k.startswith("MATRIX_")]
    for k in keys_to_remove:
        del os.environ[k]
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


@pytest.fixture
def mock_rtx4090_csv() -> str:
    return "NVIDIA GeForce RTX 4090, 24576, 550.54.14\n"


@pytest.fixture
def mock_a100_csv() -> str:
    return "NVIDIA A100-SXM4-80GB, 81920, 535.129.03\n"


@pytest.fixture
def mock_rocm_rx7900_txt() -> str:
    return """
======================= ROCm System Management Interface =======================
================================= Product Info =================================
GPU[0]          : Card series:           AMD Radeon RX 7900 XTX
GPU[0]          : Card model:            0x744c
================================== VRAM Info ===================================
GPU[0]          : Total Memory (B):      25769803776
================================================================================
"""
