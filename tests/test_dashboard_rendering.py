"""
Unit and visual tests for Unicode QR code generation and operator dashboard rendering.
"""

from scripts.hardware_detect import HardwareProfile
from scripts.onboard import render_dashboard
from scripts.qr_code import (
    generate_qr_matrix,
    render_terminal_qr,
    choose_version,
    encode_data,
)


def test_qr_code_version_selection():
    # Short text -> Version 1
    assert choose_version(5) == 1
    # Moderate text -> Version 2 or 3
    assert choose_version(25) <= 3
    # Lightning address ~30 chars -> Version 2 or 3
    assert choose_version(30) <= 3


def test_qr_code_matrix_generation():
    data = "lightning:worker@matrixcompute.io"
    modules = generate_qr_matrix(data)
    size = len(modules)
    # Size must be 4*V + 17
    assert (size - 17) % 4 == 0
    # Modules must be 2D boolean grid
    assert all(len(row) == size for row in modules)
    assert all(isinstance(cell, bool) for row in modules for cell in row)


def test_qr_code_finder_patterns():
    modules = generate_qr_matrix("test")
    # Top-left finder center (3, 3) must be True (dark)
    assert modules[3][3] is True
    # Outer ring: (0, 0) is dark
    assert modules[0][0] is True
    # Inner light border: (1, 1) is False
    assert modules[1][1] is False


def test_render_terminal_qr_blocks():
    data = "lightning:worker@matrixcompute.io"
    qr_text = render_terminal_qr(data, invert=False, quiet_zone=2)
    assert qr_text
    lines = qr_text.splitlines()
    assert len(lines) > 10

    # Ensure Unicode block characters are present
    all_chars = set("".join(lines))
    block_chars = {"▀", "▄", "█", " "}
    assert any(c in block_chars for c in all_chars)


def test_render_terminal_qr_invert():
    data = "test_qr"
    normal = render_terminal_qr(data, invert=False, quiet_zone=2)
    inverted = render_terminal_qr(data, invert=True, quiet_zone=2)
    assert normal != inverted
    assert len(normal.splitlines()) == len(inverted.splitlines())


def test_dashboard_rendering_layout():
    hw = HardwareProfile(
        vendor="NVIDIA",
        model="NVIDIA GeForce RTX 4090",
        vram_mb=24576,
        tflops=82.6,
        tee_type=None,
        is_gpu=True,
        is_tee=False,
    )
    payout = "worker@matrixcompute.io"
    npub = "npub1matrixcomputeoperator00000000000000000000000000000000000"

    dash = render_dashboard(
        payout_address=payout,
        npub=npub,
        hardware=hw,
        nat_mode="OUTBOUND-ONLY NAT",
        tier="PROBATIONARY",
    )

    assert "DISTRIBUTED MATRIX MULTIPLY — OPERATOR DASHBOARD" in dash
    assert "ONLINE (Ready for Tile Tasks)" in dash
    assert "OUTBOUND-ONLY NAT (Zero Inbound Ports)" in dash
    assert "PROBATIONARY (Auto-Bond Sweep: Active)" in dash
    assert npub in dash
    assert "NVIDIA GeForce RTX 4090" in dash
    assert "82.6 TFLOPS (FP32)" in dash
    assert payout in dash
    assert "┌" in dash
    assert "└" in dash


def test_qr_code_version_7_to_10_version_info():
    """Verify that Version 7-10 QR codes allocate version info blocks and match size requirements."""
    for v in [7, 8, 9, 10]:
        # Generate payload that triggers target version
        # V7: 107-122 bytes, V8: 123-152 bytes, V9: 153-180 bytes, V10: 181-213 bytes
        length_map = {7: 110, 8: 130, 9: 160, 10: 190}
        payload = "A" * length_map[v]
        assert choose_version(len(payload)) == v

        modules = generate_qr_matrix(payload)
        expected_size = 4 * v + 17
        assert len(modules) == expected_size
        assert all(len(row) == expected_size for row in modules)


def test_dashboard_rendering_long_lnurl():
    """Verify operator dashboard renders cleanly with a realistic 170-character LNURL (Version 9 QR)."""
    hw = HardwareProfile(
        vendor="AMD",
        model="AMD EPYC 7763 64-Core Processor (AMD SEV-SNP Enclave)",
        vram_mb=0,
        tflops=3.2,
        tee_type="AMD_SEV_SNP",
        is_gpu=False,
        is_tee=True,
    )
    long_lnurl = (
        "LNURL1DP68GURN8GHJ7MRW9E3XJUM59ACXZ7FLW4EK2UNWV9KK7MM5V9EK7AMPD3KX2AR0VEEKZAR0WD5XJTNRDAKJ7TNHV4KXCTTTDEHHWM30D3H82UNV9ACXZ7FLW4EK2UNWV9KK7MM5V9EK7AMPD3KX2AR0VEEKZAR0W"
    )
    npub = "npub1matrixcomputeoperator00000000000000000000000000000000000"

    dash = render_dashboard(
        payout_address=long_lnurl,
        npub=npub,
        hardware=hw,
        nat_mode="OUTBOUND-ONLY NAT",
        tier="PROBATIONARY",
    )

    lines = dash.splitlines()
    assert len(lines) > 25
    # Guarantee fixed 72-column border alignment across QR block rows and borders
    qr_lines = [l for l in lines if any(c in "▀▄█" for c in l)]
    assert len(qr_lines) > 0
    for idx, l in enumerate(qr_lines):
        assert len(l) == 72, f"QR line {idx} width mismatch: len={len(l)} != 72. Content: {l!r}"

    assert lines[0] == "┌" + "─" * 70 + "┐"
    assert lines[-1] == "└" + "─" * 70 + "┘"
    assert "AMD SEV-SNP" in dash
    assert "PROBATIONARY (Auto-Bond Sweep: Active)" in dash
    assert long_lnurl in dash

