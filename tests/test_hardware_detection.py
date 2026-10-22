"""
Unit and integration tests for Multi-Vendor Hardware & TEE Detection Cascade.
"""

import os
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from scripts.hardware_detect import (
    HardwareProfile,
    ROCM_DEV_PATHS,
    detect_hardware,
    estimate_nvidia_tflops,
    estimate_amd_tflops,
    _query_nvidia_smi,
    _query_amd_rocm,
    _query_amd_sev_snp,
    _query_intel_tdx,
    _query_cpu_fallback,
)


def test_detect_hardware_mock_nvidia():
    prof = detect_hardware(mock_env="nvidia")
    assert prof.vendor == "NVIDIA"
    assert "RTX 4090" in prof.model
    assert prof.vram_mb == 24576
    assert prof.tflops == 82.6
    assert prof.is_gpu is True
    assert prof.is_tee is False
    assert prof.tee_type is None


def test_detect_hardware_mock_rocm():
    prof = detect_hardware(mock_env="rocm")
    assert prof.vendor == "AMD"
    assert "RX 7900 XTX" in prof.model
    assert prof.vram_mb == 24576
    assert prof.tflops == 61.4
    assert prof.is_gpu is True
    assert prof.is_tee is False
    assert prof.tee_type is None


def test_detect_hardware_mock_sev_snp():
    prof = detect_hardware(mock_env="sev-snp")
    assert prof.vendor == "AMD"
    assert "SEV-SNP" in prof.model
    assert prof.tee_type == "AMD_SEV_SNP"
    assert prof.is_gpu is False
    assert prof.is_tee is True
    assert prof.tflops > 0


def test_detect_hardware_mock_tdx():
    prof = detect_hardware(mock_env="tdx")
    assert prof.vendor == "Intel"
    assert "TDX" in prof.model
    assert prof.tee_type == "INTEL_TDX"
    assert prof.is_gpu is False
    assert prof.is_tee is True
    assert prof.tflops > 0


def test_detect_hardware_mock_cpu():
    prof = detect_hardware(mock_env="cpu")
    assert prof.vendor == "Generic"
    assert "CPU" in prof.model
    assert prof.is_gpu is False
    assert prof.is_tee is False
    assert prof.tee_type is None
    assert prof.tflops > 0


def test_detect_hardware_env_var(clean_matrix_env):
    os.environ["MATRIX_MOCK_HARDWARE"] = "rocm"
    prof = detect_hardware()
    assert prof.vendor == "AMD"
    assert prof.is_gpu is True


def test_invalid_mock_raises_error():
    with pytest.raises(ValueError, match="Unknown mock hardware profile"):
        detect_hardware(mock_env="quantum_computer")


def test_hardware_profile_serialization():
    p1 = HardwareProfile(
        vendor="NVIDIA",
        model="NVIDIA H100 80GB HBM3",
        vram_mb=81920,
        tflops=67.0,
        tee_type=None,
        is_gpu=True,
        is_tee=False,
    )
    d = p1.to_dict()
    assert d["vendor"] == "NVIDIA"
    assert d["tflops"] == 67.0

    p2 = HardwareProfile.from_dict(d)
    assert p2.vendor == p1.vendor
    assert p2.model == p1.model
    assert p2.vram_mb == p1.vram_mb
    assert p2.tflops == p1.tflops
    assert p2.is_gpu == p1.is_gpu

    json_str = p1.to_json()
    assert '"vendor": "NVIDIA"' in json_str
    assert '"tflops": 67.0' in json_str


def test_nvidia_tflops_estimation():
    assert estimate_nvidia_tflops("NVIDIA GeForce RTX 4090") == 82.6
    assert estimate_nvidia_tflops("NVIDIA RTX 4080 Super") == 52.2
    assert estimate_nvidia_tflops("NVIDIA RTX 3090 Ti") == 40.0
    assert estimate_nvidia_tflops("NVIDIA RTX 3090") == 35.6
    assert estimate_nvidia_tflops("NVIDIA A100-SXM4-80GB") == 19.5
    assert estimate_nvidia_tflops("NVIDIA H100 PCIe") == 67.0
    assert estimate_nvidia_tflops("NVIDIA L40S") == 91.6
    # Fallback
    assert estimate_nvidia_tflops("Custom Unknown GPU") == 15.0


def test_amd_tflops_estimation():
    assert estimate_amd_tflops("AMD Radeon RX 7900 XTX") == 61.4
    assert estimate_amd_tflops("AMD Radeon RX 7900 XT") == 51.5
    assert estimate_amd_tflops("AMD Radeon RX 7800 XT") == 37.3
    assert estimate_amd_tflops("AMD Instinct MI300X OAM") == 163.4
    assert estimate_amd_tflops("AMD Instinct MI250X") == 47.9
    # Fallback
    assert estimate_amd_tflops("Custom Unknown Radeon") == 20.0


@patch("shutil.which", return_value="/usr/bin/nvidia-smi")
@patch("subprocess.run")
def test_query_nvidia_smi_parsing(mock_run, mock_which, mock_rtx4090_csv):
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = mock_rtx4090_csv
    mock_run.return_value = mock_res

    prof = _query_nvidia_smi()
    assert prof is not None
    assert prof.vendor == "NVIDIA"
    assert prof.model == "NVIDIA GeForce RTX 4090"
    assert prof.vram_mb == 24576
    assert prof.tflops == 82.6
    assert prof.is_gpu is True


@patch("shutil.which", return_value="/usr/bin/rocm-smi")
@patch("subprocess.run")
def test_query_amd_rocm_parsing(mock_run, mock_which, mock_rocm_rx7900_txt):
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = mock_rocm_rx7900_txt
    mock_run.return_value = mock_res

    prof = _query_amd_rocm()
    assert prof is not None
    assert prof.vendor == "AMD"
    assert "RX 7900 XTX" in prof.model
    assert prof.vram_mb == 24576  # 25769803776 bytes // (1024*1024)
    assert prof.tflops == 61.4
    assert prof.is_gpu is True


@patch("os.path.exists")
def test_query_amd_sev_snp(mock_exists):
    def exists_side_effect(p):
        return p == "/dev/sev-guest"

    mock_exists.side_effect = exists_side_effect
    prof = _query_amd_sev_snp()
    assert prof is not None
    assert prof.vendor == "AMD"
    assert prof.tee_type == "AMD_SEV_SNP"
    assert prof.is_tee is True
    assert prof.is_gpu is False


@patch("os.path.exists")
def test_query_intel_tdx(mock_exists):
    def exists_side_effect(p):
        return p == "/dev/tdx_guest"

    mock_exists.side_effect = exists_side_effect
    prof = _query_intel_tdx()
    assert prof is not None
    assert prof.vendor == "Intel"
    assert prof.tee_type == "INTEL_TDX"
    assert prof.is_tee is True
    assert prof.is_gpu is False


def test_query_cpu_fallback():
    prof = _query_cpu_fallback()
    assert prof is not None
    assert prof.is_gpu is False
    assert prof.is_tee is False
    assert prof.tflops >= 0.1


@patch("shutil.which", return_value="/usr/bin/rocm-smi")
@patch("subprocess.run")
def test_query_amd_rocm_empty_or_no_devices(mock_run, mock_which):
    """Verify rocm-smi returning exit code 0 but no devices returns None."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "No ROCm SMI devices found\n"
    mock_run.return_value = mock_res

    prof = _query_amd_rocm()
    assert prof is None


def test_rocm_dev_paths_excludes_generic_drm():
    """Verify ROCM_DEV_PATHS contains only /dev/kfd and excludes generic /dev/dri/renderD128."""
    assert "/dev/kfd" in ROCM_DEV_PATHS
    assert "/dev/dri/renderD128" not in ROCM_DEV_PATHS


@patch("shutil.which", return_value=None)
@patch("os.path.exists")
def test_detect_hardware_drm_node_does_not_mask_sev_snp(mock_exists, mock_which):
    """Verify standard Linux DRM render node does not suppress SEV-SNP detection."""
    def exists_side_effect(p):
        return p in ("/dev/sev-guest", "/dev/dri/renderD128")

    mock_exists.side_effect = exists_side_effect
    prof = detect_hardware()
    assert prof.is_gpu is False
    assert prof.is_tee is True
    assert prof.tee_type == "AMD_SEV_SNP"


@patch("shutil.which", return_value=None)
@patch("os.path.exists")
def test_detect_hardware_drm_node_does_not_mask_intel_tdx(mock_exists, mock_which):
    """Verify standard Linux DRM render node does not suppress Intel TDX detection."""
    def exists_side_effect(p):
        return p in ("/dev/tdx_guest", "/dev/dri/renderD128")

    mock_exists.side_effect = exists_side_effect
    prof = detect_hardware()
    assert prof.is_gpu is False
    assert prof.is_tee is True
    assert prof.tee_type == "INTEL_TDX"


@patch("shutil.which", return_value=None)
@patch("os.path.exists")
def test_detect_hardware_drm_node_falls_back_to_cpu(mock_exists, mock_which):
    """Verify host with only generic DRM render node cleanly falls back to CPU."""
    def exists_side_effect(p):
        return p == "/dev/dri/renderD128"

    mock_exists.side_effect = exists_side_effect
    prof = detect_hardware()
    assert prof.is_gpu is False
    assert prof.is_tee is False
    assert prof.tee_type is None
    assert prof.model
    assert prof.tflops > 0

