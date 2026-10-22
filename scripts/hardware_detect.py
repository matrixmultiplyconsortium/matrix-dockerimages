#!/usr/bin/env python3
"""
Multi-Vendor Hardware & TEE Detection Engine for Distributed Matrix Multiply Workers.

Implements a 5-profile detection cascade:
1. NVIDIA GPU (via nvidia-smi / NVML)
2. AMD ROCm GPU (via rocm-smi / /dev/kfd)
3. AMD SEV-SNP Confidential VM (/dev/sev-guest, /dev/sev_guest)
4. Intel TDX Confidential VM (/dev/tdx_guest, /dev/tdx-guest, /dev/tdx-attest)
5. CPU Fallback (multi-core host CPU)

Includes deterministic --mock support for offline hermetic testing.
"""

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

SEV_SNP_DEV_PATHS: List[str] = [
    "/dev/sev-guest",
    "/dev/sev_guest",
    "/sys/devices/virtual/misc/sev-guest",
]

TDX_DEV_PATHS: List[str] = [
    "/dev/tdx_guest",
    "/dev/tdx-guest",
    "/dev/tdx-attest",
    "/sys/devices/virtual/misc/tdx_guest",
    "/sys/kernel/security/tdx",
]

ROCM_DEV_PATHS: List[str] = [
    "/dev/kfd",
]

# Curated FP32 TFLOPS lookup table: (Regex Pattern, Peak FP32 TFLOPS)
CURATED_NVIDIA_FP32_TFLOPS: List[Tuple[str, float]] = [
    (r"H(?:100|200)", 67.0),
    (r"L40S\b", 91.6),
    (r"L40\b", 90.5),
    (r"(?:RTX\s*)?6000\s*Ada", 91.1),
    (r"L4\b", 30.3),
    (r"4090\b", 82.6),
    (r"4080\s*Super\b", 52.2),
    (r"4080\b", 48.7),
    (r"4070\s*Ti\s*Super\b", 44.1),
    (r"4070\s*Ti\b", 40.1),
    (r"4070\s*Super\b", 35.5),
    (r"4070\b", 29.0),
    (r"4060\s*Ti\b", 22.1),
    (r"4060\b", 15.1),
    (r"A100\b", 19.5),
    (r"A40\b", 37.4),
    (r"A10(?:G)?\b", 31.2),
    (r"A30\b", 10.3),
    (r"(?:RTX\s*)?A6000\b", 38.7),
    (r"3090\s*Ti\b", 40.0),
    (r"3090\b", 35.6),
    (r"3080\s*Ti\b", 34.1),
    (r"3080\b", 29.8),
    (r"3070\s*Ti\b", 21.7),
    (r"3070\b", 20.3),
    (r"3060\s*Ti\b", 16.2),
    (r"3060\b", 12.7),
    (r"V100\b", 15.7),
    (r"T4\b", 8.1),
    (r"2080\s*Ti\b", 13.4),
    (r"2080\s*Super\b", 11.1),
    (r"2080\b", 10.1),
    (r"2070\b", 7.5),
    (r"2060\b", 6.5),
]

CURATED_AMD_FP32_TFLOPS: List[Tuple[str, float]] = [
    (r"MI300[AX]?\b", 163.4),
    (r"MI250X?\b", 47.9),
    (r"MI210\b", 45.3),
    (r"MI100\b", 23.1),
    (r"7900\s*XTX\b", 61.4),
    (r"7900\s*XT\b", 51.5),
    (r"7900\s*GRE\b", 46.0),
    (r"7800\s*XT\b", 37.3),
    (r"7700\s*XT\b", 35.2),
    (r"6950\s*XT\b", 23.7),
    (r"6900\s*XT\b", 23.0),
    (r"6800\s*XT\b", 20.7),
]


@dataclasses.dataclass
class HardwareProfile:
    """Structured compute hardware and confidential computing profile."""
    vendor: str
    model: str
    vram_mb: int
    tflops: float
    tee_type: Optional[str] = None
    is_gpu: bool = False
    is_tee: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor": self.vendor,
            "model": self.model,
            "vram_mb": self.vram_mb,
            "tflops": self.tflops,
            "tee_type": self.tee_type,
            "is_gpu": self.is_gpu,
            "is_tee": self.is_tee,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HardwareProfile":
        return cls(
            vendor=data["vendor"],
            model=data["model"],
            vram_mb=int(data["vram_mb"]),
            tflops=float(data["tflops"]),
            tee_type=data.get("tee_type"),
            is_gpu=bool(data.get("is_gpu", False)),
            is_tee=bool(data.get("is_tee", False)),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def estimate_nvidia_tflops(model_name: str) -> float:
    """Match GPU model name against curated lookup table or provide safe fallback."""
    for pattern, tflops in CURATED_NVIDIA_FP32_TFLOPS:
        if re.search(pattern, model_name, re.IGNORECASE):
            return tflops
    return 15.0


def estimate_amd_tflops(model_name: str) -> float:
    """Match AMD GPU model name against curated lookup table or provide safe fallback."""
    for pattern, tflops in CURATED_AMD_FP32_TFLOPS:
        if re.search(pattern, model_name, re.IGNORECASE):
            return tflops
    return 20.0


def _query_nvidia_smi() -> Optional[HardwareProfile]:
    """Tier 1: Query local NVIDIA GPU via nvidia-smi."""
    nvidia_smi_bin = shutil.which("nvidia-smi")
    if not nvidia_smi_bin:
        # Check standard Windows paths if on Windows
        win_path = r"C:\Windows\System32\nvidia-smi.exe"
        if os.path.exists(win_path):
            nvidia_smi_bin = win_path
        else:
            return None

    try:
        cmd = [
            nvidia_smi_bin,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode != 0 or not res.stdout.strip():
            return None

        line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            model = parts[0]
            try:
                vram_mb = int(float(parts[1]))
            except ValueError:
                vram_mb = 0
            tflops = estimate_nvidia_tflops(model)
            return HardwareProfile(
                vendor="NVIDIA",
                model=model,
                vram_mb=vram_mb,
                tflops=tflops,
                tee_type=None,
                is_gpu=True,
                is_tee=False,
            )
    except Exception:
        pass
    return None


def _query_amd_rocm() -> Optional[HardwareProfile]:
    """Tier 2: Query AMD ROCm GPU via rocm-smi or /dev/kfd."""
    rocm_smi_bin = shutil.which("rocm-smi")
    if not rocm_smi_bin:
        for p in ["/opt/rocm/bin/rocm-smi", "/opt/rocm/bin/rocminfo"]:
            if os.path.exists(p):
                rocm_smi_bin = p
                break

    if rocm_smi_bin:
        try:
            cmd = [rocm_smi_bin, "--showproductname", "--showmeminfo", "vram"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                output = res.stdout
                model_match = re.search(r"Card series:\s*(.+)", output, re.IGNORECASE)
                if not model_match:
                    model_match = re.search(r"Product Name:\s*(.+)", output, re.IGNORECASE)

                vram_match = re.search(r"Total Memory.*?:\s*(\d+)", output, re.IGNORECASE)

                # Only construct profile if rocm-smi actually identified GPU hardware.
                # Avoid false positives on 'No ROCm SMI devices found'.
                if model_match or vram_match:
                    model = model_match.group(1).strip() if model_match else "AMD Radeon / Instinct GPU"
                    vram_mb = 16384
                    if vram_match:
                        try:
                            raw_vram = int(vram_match.group(1))
                            # Check if reported in bytes or MB
                            vram_mb = raw_vram // (1024 * 1024) if raw_vram > 1000000 else raw_vram
                        except ValueError:
                            pass

                    tflops = estimate_amd_tflops(model)
                    return HardwareProfile(
                        vendor="AMD",
                        model=model,
                        vram_mb=vram_mb,
                        tflops=tflops,
                        tee_type=None,
                        is_gpu=True,
                        is_tee=False,
                    )
        except Exception:
            pass

    # Fallback to checking /dev/kfd device node
    for dev_path in ROCM_DEV_PATHS:
        if os.path.exists(dev_path):
            return HardwareProfile(
                vendor="AMD",
                model="AMD ROCm Compute Device (/dev/kfd)",
                vram_mb=16384,
                tflops=25.0,
                tee_type=None,
                is_gpu=True,
                is_tee=False,
            )
    return None


def _query_amd_sev_snp() -> Optional[HardwareProfile]:
    """Tier 3: Check AMD SEV-SNP Confidential Computing VM."""
    for dev_path in SEV_SNP_DEV_PATHS:
        if os.path.exists(dev_path):
            cpu_model, cores = _get_cpu_info()
            return HardwareProfile(
                vendor="AMD",
                model=f"{cpu_model} (AMD SEV-SNP Enclave)",
                vram_mb=0,
                tflops=round(max(0.5, cores * 0.05), 2),
                tee_type="AMD_SEV_SNP",
                is_gpu=False,
                is_tee=True,
            )
    return None


def _query_intel_tdx() -> Optional[HardwareProfile]:
    """Tier 4: Check Intel TDX Confidential Computing VM."""
    for dev_path in TDX_DEV_PATHS:
        if os.path.exists(dev_path):
            cpu_model, cores = _get_cpu_info()
            return HardwareProfile(
                vendor="Intel",
                model=f"{cpu_model} (Intel TDX Enclave)",
                vram_mb=0,
                tflops=round(max(0.5, cores * 0.05), 2),
                tee_type="INTEL_TDX",
                is_gpu=False,
                is_tee=True,
            )
    return None


def _get_cpu_info() -> Tuple[str, int]:
    """Determine host CPU model name and logical core count."""
    cores = os.cpu_count() or 4
    model = "Generic Multi-Core CPU"

    # Linux /proc/cpuinfo
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("model name") or line.startswith("Model"):
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            model = parts[1].strip()
                            break
            return model, cores
        except Exception:
            pass

    # Windows Registry
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if val and str(val).strip():
                return str(val).strip(), cores
        except Exception:
            pass

    # macOS sysctl
    if sys.platform == "darwin":
        try:
            res = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip(), cores
        except Exception:
            pass

    return model, cores


def _query_cpu_fallback() -> HardwareProfile:
    """Tier 5: Fallback to host CPU execution."""
    model, cores = _get_cpu_info()
    vendor = "Intel" if "intel" in model.lower() else ("AMD" if "amd" in model.lower() else "CPU")
    tflops = round(max(0.2, cores * 0.05), 2)
    return HardwareProfile(
        vendor=vendor,
        model=model,
        vram_mb=0,
        tflops=tflops,
        tee_type=None,
        is_gpu=False,
        is_tee=False,
    )


def detect_hardware(mock_env: Optional[str] = None) -> HardwareProfile:
    """
    Execute 5-profile hardware cascade:
    NVIDIA GPU -> AMD ROCm GPU -> AMD SEV-SNP -> Intel TDX -> CPU Fallback.

    Supports mock_env ('nvidia', 'rocm', 'sev-snp', 'tdx', 'cpu') for deterministic offline tests.
    """
    # Environment variable fallback for mock
    if not mock_env:
        mock_env = os.environ.get("MATRIX_MOCK_HARDWARE")

    if mock_env:
        clean = mock_env.strip().lower()
        if clean in ("nvidia", "cuda"):
            return HardwareProfile(
                vendor="NVIDIA",
                model="NVIDIA GeForce RTX 4090",
                vram_mb=24576,
                tflops=82.6,
                tee_type=None,
                is_gpu=True,
                is_tee=False,
            )
        elif clean in ("rocm", "amd", "amd-gpu"):
            return HardwareProfile(
                vendor="AMD",
                model="AMD Radeon RX 7900 XTX",
                vram_mb=24576,
                tflops=61.4,
                tee_type=None,
                is_gpu=True,
                is_tee=False,
            )
        elif clean in ("sev-snp", "sev_snp", "sevsnp"):
            return HardwareProfile(
                vendor="AMD",
                model="AMD EPYC 7763 64-Core Processor (AMD SEV-SNP Enclave)",
                vram_mb=0,
                tflops=3.2,
                tee_type="AMD_SEV_SNP",
                is_gpu=False,
                is_tee=True,
            )
        elif clean in ("tdx", "intel-tdx"):
            return HardwareProfile(
                vendor="Intel",
                model="Intel Xeon Platinum 8480+ (Intel TDX Enclave)",
                vram_mb=0,
                tflops=2.8,
                tee_type="INTEL_TDX",
                is_gpu=False,
                is_tee=True,
            )
        elif clean in ("cpu", "fallback"):
            return HardwareProfile(
                vendor="Generic",
                model="Generic Multi-Core CPU Fallback",
                vram_mb=0,
                tflops=0.8,
                tee_type=None,
                is_gpu=False,
                is_tee=False,
            )
        else:
            raise ValueError(f"Unknown mock hardware profile: {mock_env}. Supported: nvidia, rocm, sev-snp, tdx, cpu")

    # Tier 1: NVIDIA
    prof = _query_nvidia_smi()
    if prof:
        return prof

    # Tier 2: AMD ROCm
    prof = _query_amd_rocm()
    if prof:
        return prof

    # Tier 3: AMD SEV-SNP
    prof = _query_amd_sev_snp()
    if prof:
        return prof

    # Tier 4: Intel TDX
    prof = _query_intel_tdx()
    if prof:
        return prof

    # Tier 5: CPU Fallback
    return _query_cpu_fallback()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Vendor Hardware & TEE Detection Engine")
    parser.add_argument(
        "--mock",
        type=str,
        choices=["nvidia", "rocm", "sev-snp", "tdx", "cpu"],
        help="Simulate hardware detection for deterministic testing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Output profile in JSON format (default: True)",
    )
    args = parser.parse_args()

    profile = detect_hardware(mock_env=args.mock)
    print(profile.to_json())


if __name__ == "__main__":
    main()
