"""
Adversarial Stress & Empirical Challenge Suite for Milestone 1 (matrix-dockerimages).

Challenges and stress-tests:
1. Pure-Python QR code generator (scripts/qr_code.py):
   - Extreme string lengths (0 to 213 chars, boundary checks, capacity overflow).
   - Diverse character sets (numeric, alphanumeric, binary bytes, URLs, LNURLs, UTF-8).
   - Reed-Solomon GF(2^8) generator polynomials and polynomial remainder math against ISO 18004 test vectors.
   - Unicode half-block packing and rendering stability.
   - ISO/IEC 18004 Section 6.5.2 Version Information pattern verification (Versions 7 to 10).
2. Multi-vendor hardware & TEE detection cascade (scripts/hardware_detect.py):
   - Corrupt, truncated, and [N/A] nvidia-smi outputs.
   - rocm-smi false positive when no GPUs exist ("No ROCm SMI devices found").
   - Non-AMD /dev/dri/renderD128 false positive.
   - Simultaneous device nodes and TEE (SEV-SNP / TDX) suppression/masking.
   - Non-standard CPU formats (ARM, empty cpuinfo).
"""

import os
import re
import sys
from unittest.mock import MagicMock, patch
import pytest

from scripts.hardware_detect import (
    HardwareProfile,
    detect_hardware,
    _query_nvidia_smi,
    _query_amd_rocm,
    _query_amd_sev_snp,
    _query_intel_tdx,
    _get_cpu_info,
    _query_cpu_fallback,
    ROCM_DEV_PATHS,
)
from scripts.qr_code import (
    choose_version,
    encode_data,
    generate_qr_matrix,
    render_terminal_qr,
    rs_compute_ec,
    rs_generator_poly,
    gf_mul,
    VERSION_SPECS_M,
    QRCodeMatrix,
)


# ==============================================================================
# SECTION 1: QR Code Stress Tests (Lengths, Charsets, RS Math, Half-Blocks)
# ==============================================================================

def test_stress_qr_extreme_string_lengths():
    """Verify QR code version selection and generation across extreme lengths."""
    # 0 length (empty string)
    assert choose_version(0) == 1
    m0 = generate_qr_matrix("")
    assert len(m0) == 21

    # Single character
    assert choose_version(1) == 1
    m1 = generate_qr_matrix("x")
    assert len(m1) == 21

    # Exact boundary tests for versions 1 to 10 in Byte Mode Level M
    # Max payload bytes for each version:
    # V1: 14, V2: 26, V3: 42, V4: 62, V5: 84, V6: 106, V7: 122, V8: 152, V9: 180, V10: 213
    boundaries = [
        (1, 14), (2, 26), (3, 42), (4, 62), (5, 84),
        (6, 106), (7, 122), (8, 152), (9, 180), (10, 213)
    ]
    for ver, max_len in boundaries:
        payload = "A" * max_len
        selected_ver = choose_version(len(payload.encode("utf-8")))
        assert selected_ver == ver, f"Expected V{ver} for length {max_len}, got V{selected_ver}"
        matrix = generate_qr_matrix(payload)
        expected_size = 4 * ver + 17
        assert len(matrix) == expected_size
        assert all(len(row) == expected_size for row in matrix)

    # 214 bytes exceeds max Version 10 capacity
    with pytest.raises(ValueError, match="exceeds max supported QR version 10 capacity"):
        choose_version(214)

    # 1000 bytes also cleanly raises ValueError
    with pytest.raises(ValueError, match="exceeds max supported QR version 10 capacity"):
        choose_version(1000)


def test_stress_qr_diverse_character_sets():
    """Verify QR matrix generation across diverse character sets and encodings."""
    test_strings = [
        "12345678901234567890",  # Numeric
        "MATRIXCOMPUTEWORKER01",  # Alphanumeric uppercase
        "matrix:worker@matrix-compute.com",  # Mixed email/URI
        "https://matrix-compute.com/tasks/tile?id=8372&x=12&y=34",  # Standard URL
        "lnbc250u1p3...lightning...invoice...",  # Lightning invoice prefix
        "LNURL1DP68GURN8GHJ7MRW9E3XJUM59ACXZ7FLW4EK2UNWV9KK7MM5V9EK7AMPD3KX2AR0VEEKZAR0W",  # LNURL
        "⚡₿🔥🚀💻",  # Emojis (multi-byte UTF-8)
        "你好世界，矩阵乘法计算节点",  # Chinese characters (3-byte UTF-8)
        "accentué_téléport_münchen",  # Latin accented characters
        "".join(chr(i) for i in range(32, 127)),  # Full printable ASCII set
    ]
    for s in test_strings:
        matrix = generate_qr_matrix(s)
        size = len(matrix)
        assert size >= 21
        assert (size - 17) % 4 == 0
        qr_text = render_terminal_qr(s)
        assert len(qr_text.splitlines()) > 0


def test_stress_qr_reed_solomon_iso18004_test_vectors():
    """Verify Reed-Solomon GF(2^8) generator polynomial and remainder math against ISO 18004 Annex A."""
    # ISO/IEC 18004 Annex A Example 1 (Version 1, EC Level M: 16 data codewords, 10 EC codewords)
    iso_data = [
        0x10, 0x20, 0x0C, 0x56, 0x61, 0x80, 0xEC, 0x11,
        0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11
    ]
    expected_iso_ec = [165, 36, 212, 193, 237, 54, 199, 135, 44, 85]
    computed_ec = rs_compute_ec(iso_data, 10)
    assert computed_ec == expected_iso_ec, f"RS mismatch: got {computed_ec}, expected {expected_iso_ec}"


def test_stress_qr_reed_solomon_generator_degrees():
    """Verify generator polynomial degrees and leading coefficients."""
    for ec_count in [7, 10, 14, 16, 18, 20, 22, 24, 26, 28, 30]:
        gen = rs_generator_poly(ec_count)
        # Degree of generator polynomial must be ec_count, having ec_count + 1 terms
        assert len(gen) == ec_count + 1
        # Leading coefficient of generator polynomial in standard form is 1
        assert gen[0] == 1


def test_stress_qr_terminal_rendering_half_blocks():
    """Verify Unicode half-block packing, line count arithmetic, and invert toggle."""
    data = "worker@matrix-compute.com"
    for qz in [0, 1, 2, 4]:
        rendered = render_terminal_qr(data, invert=False, quiet_zone=qz)
        lines = rendered.splitlines()
        modules = generate_qr_matrix(data)
        padded_size = len(modules) + 2 * qz
        expected_line_count = (padded_size + 1) // 2
        assert len(lines) == expected_line_count
        assert all(len(line) == padded_size for line in lines)

        # Characters must only be from the allowed block characters set
        allowed_chars = {"▀", "▄", "█", " "}
        for line in lines:
            assert all(c in allowed_chars for c in line)


# ==============================================================================
# SECTION 2: Empirical Challenge Tests (Uncovering Real Bugs)
# ==============================================================================

def test_challenge_qr_version_info_missing_v7_to_v10():
    """
    VERIFICATION OF REMEDY (ISO/IEC 18004 Section 6.5.2):
    Verify that Version 7 through 10 QR codes correctly reserve both 3x6 rectangles
    (36 modules total) and place the standard 18-bit BCH version information strings.
    """
    ISO_VERSION_INFO = {
        7: 0x07C94,
        8: 0x085BC,
        9: 0x09A99,
        10: 0x0A4D3,
    }

    for v in [7, 8, 9, 10]:
        matrix = QRCodeMatrix(v)
        matrix.place_finder(0, 0)
        matrix.place_finder(0, matrix.size - 7)
        matrix.place_finder(matrix.size - 7, 0)
        matrix.place_timing()
        matrix.place_alignment()
        matrix.reserve_format_info()

        # Check if the 3x6 version information rectangles are reserved:
        # 1. Top-right version info block: rows 0..5, cols size-11..size-9
        tr_reserved = [
            matrix.reserved[r][c]
            for r in range(6)
            for c in range(matrix.size - 11, matrix.size - 8)
        ]
        # 2. Bottom-left version info block: rows size-11..size-9, cols 0..5
        bl_reserved = [
            matrix.reserved[r][c]
            for r in range(matrix.size - 11, matrix.size - 8)
            for c in range(6)
        ]

        # In a compliant ISO/IEC 18004 implementation, all 36 modules MUST be reserved.
        unreserved_count = tr_reserved.count(False) + bl_reserved.count(False)
        assert unreserved_count == 0, f"V{v}: Expected 36 reserved modules, got unreserved: {unreserved_count}"

        # Place version info and verify placed bit values match ISO 18004 BCH codes
        matrix.place_version_info()
        expected_code = ISO_VERSION_INFO[v]
        expected_bits = [(expected_code >> i) & 1 for i in range(18)]

        # Check top-right: row i // 3, col size - 11 + (i % 3)
        tr_bits = [
            int(matrix.modules[i // 3][matrix.size - 11 + (i % 3)])
            for i in range(18)
        ]
        assert tr_bits == expected_bits, f"V{v} top-right version info bits mismatch"

        # Check bottom-left: row size - 11 + (i % 3), col i // 3
        bl_bits = [
            int(matrix.modules[matrix.size - 11 + (i % 3)][i // 3])
            for i in range(18)
        ]
        assert bl_bits == expected_bits, f"V{v} bottom-left version info bits mismatch"


def test_challenge_qr_v7_to_v10_matrix_diffs_vs_iso18004():
    """
    VERIFICATION OF REMEDY (Bit-for-Bit ISO 18004 Conformance):
    Compares generate_qr_matrix() against reference ISO/IEC 18004 module layout.
    All versions 1 through 10 MUST produce EXACT 0 module differences.
    """
    pytest.importorskip("qrcode")
    import qrcode
    import qrcode.util

    diff_table = {}
    for v in range(1, 11):
        spec = VERSION_SPECS_M[v]
        total_data = spec[1]
        hdr_bytes = 2 if v < 10 else 3
        payload = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" * 10)[:total_data - hdr_bytes - 1]

        qr = qrcode.QRCode(version=v, error_correction=qrcode.constants.ERROR_CORRECT_M, mask_pattern=0)
        data_obj = qrcode.util.QRData(payload.encode("utf-8"), mode=qrcode.util.MODE_8BIT_BYTE)
        qr.add_data(data_obj)
        qr.make(fit=False)

        our_modules = generate_qr_matrix(payload, version=v)

        diffs = 0
        for r in range(len(our_modules)):
            for c in range(len(our_modules)):
                if bool(our_modules[r][c]) != bool(qr.modules[r][c]):
                    diffs += 1
        diff_table[v] = diffs

    # All versions 1 to 10 must have EXACTLY 0 differences against ISO reference
    for v in range(1, 11):
        assert diff_table[v] == 0, f"Expected 0 diffs for V{v}, got {diff_table[v]}"


def test_stress_hardware_detect_corrupt_nvidia_smi():
    """Verify hardware detection resilience against truncated and corrupt nvidia-smi outputs."""
    with patch("shutil.which", return_value="/usr/bin/nvidia-smi"), patch("subprocess.run") as mock_run:
        # Case 1: Truncated output (only model, missing memory and driver fields)
        mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA GeForce RTX 4090\n")
        assert _query_nvidia_smi() is None

        # Case 2: [N/A] reported for total memory
        mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA GeForce RTX 4090, [N/A], 535.104\n")
        prof = _query_nvidia_smi()
        assert prof is not None
        assert prof.vram_mb == 0
        assert prof.vendor == "NVIDIA"

        # Case 3: Empty whitespace stdout
        mock_run.return_value = MagicMock(returncode=0, stdout="   \n")
        assert _query_nvidia_smi() is None

        # Case 4: Non-zero exit code
        mock_run.return_value = MagicMock(returncode=127, stdout="nvidia-smi not found\n")
        assert _query_nvidia_smi() is None

        # Case 5: Command timeout
        mock_run.side_effect = TimeoutError("Timed out")
        assert _query_nvidia_smi() is None


def test_challenge_hardware_detect_rocm_smi_false_positive():
    """
    VERIFICATION OF REMEDY:
    When rocm-smi returns returncode 0 with 'No ROCm SMI devices found',
    _query_amd_rocm() MUST return None rather than synthesizing a phantom GPU.
    """
    with patch("shutil.which", return_value="/opt/rocm/bin/rocm-smi"), \
         patch("subprocess.run") as mock_run, \
         patch("os.path.exists", return_value=False):
        # rocm-smi exits 0 but finds no AMD devices
        mock_run.return_value = MagicMock(returncode=0, stdout="No ROCm SMI devices found\n")
        prof = _query_amd_rocm()

        # Remediated behavior: returns None on empty SMI device list
        assert prof is None, "Expected None when rocm-smi finds no devices"


def test_challenge_hardware_detect_renderD128_false_positive_and_tee_masking():
    """
    VERIFICATION OF REMEDY:
    /dev/dri/renderD128 is NOT in ROCM_DEV_PATHS.
    When /dev/dri/renderD128 is present alongside /dev/sev-guest,
    detect_hardware() correctly identifies AMD SEV-SNP without suppression.
    """
    assert "/dev/dri/renderD128" not in ROCM_DEV_PATHS, "Generic DRM node must not be in ROCM_DEV_PATHS"
    assert "/dev/kfd" in ROCM_DEV_PATHS, "/dev/kfd must remain in ROCM_DEV_PATHS"
    assert ROCM_DEV_PATHS == ["/dev/kfd"], "ROCM_DEV_PATHS must strictly be ['/dev/kfd']"

    # Simulate an AMD SEV-SNP Confidential VM with standard Linux DRM render node
    def mock_dev_exists(path):
        return path in ("/dev/sev-guest", "/dev/dri/renderD128")

    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", side_effect=mock_dev_exists):
        prof = detect_hardware()

        assert prof.vendor == "AMD"
        assert prof.is_gpu is False
        assert prof.is_tee is True
        assert prof.tee_type == "AMD_SEV_SNP"
        assert "SEV-SNP" in prof.model


def test_stress_hardware_detect_nonstandard_cpuinfo():
    """Verify CPU fallback on ARM / non-standard /proc/cpuinfo formats."""
    arm_cpuinfo = """processor\t: 0
BogoMIPS\t: 48.00
Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics
CPU implementer\t: 0x41
CPU architecture: 8
CPU variant\t: 0x3
CPU part\t: 0xd0c
CPU revision\t: 1
"""
    from unittest.mock import mock_open
    with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=arm_cpuinfo)):
        model, cores = _get_cpu_info()
        assert model == "Generic Multi-Core CPU"
        assert cores > 0

        prof = _query_cpu_fallback()
        assert prof.is_gpu is False
        assert prof.is_tee is False
        assert prof.tflops >= 0.1
