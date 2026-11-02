#!/usr/bin/env python3
"""
Worker Onboarding CLI Helper for Distributed Matrix Multiply.

Provides three primary CLI commands:
1. probe: Multi-vendor hardware & TEE detection (JSON output)
2. keygen: Nostr Secp256k1 identity generation (npub/nsec/hex) & file persistence
3. dashboard: ANSI/Unicode operator dashboard with embedded Lightning payout QR code
"""

import argparse
import json
import os
import secrets
import stat
import sys
from typing import Any, Dict, List, Optional, Tuple

from scripts.hardware_detect import HardwareProfile, detect_hardware
from scripts.qr_code import render_terminal_qr

# BIP-173 Bech32 Encoding & Decoding for Nostr (NIP-19)
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_CHARSET_MAP = {c: i for i, c in enumerate(BECH32_CHARSET)}
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _bech32_polymod(values: List[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for val in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ val
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> List[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> Optional[List[int]]:
    acc = 0
    bits = 0
    ret: List[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def bech32_encode(hrp: str, data_bytes: bytes) -> str:
    """Encode arbitrary bytes into Bech32 format with the specified HRP."""
    data5 = _convertbits(data_bytes, 8, 5, True)
    if data5 is None:
        raise ValueError("Failed to convert bits for Bech32 encoding")
    values = _bech32_hrp_expand(hrp) + data5
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in (data5 + checksum))


def bech32_decode(bech_str: str) -> Tuple[str, bytes]:
    """Decode a Bech32 string into (hrp, raw_bytes). Verifies checksum."""
    clean = bech_str.strip().lower()
    pos = clean.rfind("1")
    if pos < 1 or pos + 7 > len(clean):
        raise ValueError("Invalid Bech32 separator position")
    hrp = clean[:pos]
    data_chars = clean[pos + 1 :]
    for c in data_chars:
        if c not in BECH32_CHARSET_MAP:
            raise ValueError(f"Invalid Bech32 character '{c}'")
    data5 = [BECH32_CHARSET_MAP[c] for c in data_chars]
    values = _bech32_hrp_expand(hrp) + data5
    if _bech32_polymod(values) != 1:
        raise ValueError("Invalid Bech32 checksum")
    payload5 = data5[:-6]
    acc = 0
    bits = 0
    ret = bytearray()
    for val in payload5:
        acc = (acc << 5) | val
        bits += 5
        while bits >= 8:
            bits -= 8
            ret.append((acc >> bits) & 0xFF)
    return hrp, bytes(ret)


def generate_keypair(privkey_hex: Optional[str] = None) -> Dict[str, str]:
    """
    Generate or import a Nostr Secp256k1 keypair.
    Returns dictionary with 'hex_privkey', 'hex_pubkey', 'npub', 'nsec'.
    """
    if privkey_hex is None or not str(privkey_hex).strip():
        privkey_int = secrets.randbelow(SECP256K1_ORDER - 1) + 1
    else:
        clean = str(privkey_hex).strip().lower()
        if len(clean) != 64:
            raise ValueError(f"Private key hex must be 64 characters (32 bytes), got {len(clean)}")
        try:
            privkey_int = int(clean, 16)
        except ValueError:
            raise ValueError("Private key contains invalid hexadecimal characters")
        if not (1 <= privkey_int < SECP256K1_ORDER):
            raise ValueError("Private key scalar out of range [1, SECP256K1_ORDER - 1]")

    privkey_bytes = privkey_int.to_bytes(32, "big")

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        priv_obj = ec.derive_private_key(privkey_int, ec.SECP256K1())
        pub_obj = priv_obj.public_key()
        compressed_pub = pub_obj.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.CompressedPoint,
        )
        # Nostr X-only pubkey (32 bytes)
        x_only_pub = compressed_pub[1:33]
    except ImportError:
        # Fallback using pure-Python elliptic curve math for Secp256k1
        P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
        Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

        def ec_add(p1: Optional[Tuple[int, int]], p2: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
            if p1 is None:
                return p2
            if p2 is None:
                return p1
            x1, y1 = p1
            x2, y2 = p2
            if x1 == x2 and y1 != y2:
                return None
            if x1 == x2:
                m = (3 * x1 * x1 * pow(2 * y1, P - 2, P)) % P
            else:
                m = ((y2 - y1) * pow(x2 - x1, P - 2, P)) % P
            x3 = (m * m - x1 - x2) % P
            y3 = (m * (x1 - x3) - y1) % P
            return (x3, y3)

        def ec_mul(k: int, p: Tuple[int, int]) -> Tuple[int, int]:
            curr: Optional[Tuple[int, int]] = p
            res: Optional[Tuple[int, int]] = None
            while k > 0:
                if k & 1:
                    res = ec_add(res, curr)
                curr = ec_add(curr, curr)
                k >>= 1
            if res is None:
                raise RuntimeError("Invalid point at infinity")
            return res

        qx, _ = ec_mul(privkey_int, (Gx, Gy))
        x_only_pub = qx.to_bytes(32, "big")

    npub = bech32_encode("npub", x_only_pub)
    nsec = bech32_encode("nsec", privkey_bytes)

    return {
        "hex_privkey": privkey_bytes.hex(),
        "hex_pubkey": x_only_pub.hex(),
        "npub": npub,
        "nsec": nsec,
    }


def write_env_file(filepath: str, keypair: Dict[str, str], payout_addr: str = "") -> None:
    """Save keypair configuration to an environment file with restricted permissions (0600 on POSIX)."""
    abs_path = os.path.abspath(os.path.expanduser(filepath))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    content = (
        f"# Distributed Matrix Multiply Compute Worker Configuration\n"
        f"MATRIX_WORKER_PRIVKEY={keypair['hex_privkey']}\n"
        f"MATRIX_WORKER_NSEC={keypair['nsec']}\n"
        f"MATRIX_WORKER_PUBKEY={keypair['hex_pubkey']}\n"
        f"MATRIX_WORKER_NPUB={keypair['npub']}\n"
        f"MATRIX_WORKER_PAYOUT_ADDRESS={payout_addr}\n"
        f"MATRIX_WORKER_NAT_MODE=reverse_tunnel\n"
    )

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Set restricted file permissions on POSIX
    if os.name == "posix":
        try:
            os.chmod(abs_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def render_dashboard(
    payout_address: str,
    npub: str,
    hardware: HardwareProfile,
    nat_mode: str = "OUTBOUND-ONLY NAT",
    tier: str = "PROBATIONARY",
    invert_qr: bool = False,
) -> str:
    """Format and render the full ASCII/Unicode operator dashboard with embedded Lightning QR code."""
    # Ensure stdout handles UTF-8 on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    qr_target = payout_address if payout_address else f"lightning:{npub}@matrix-compute.com"
    qr_text = render_terminal_qr(qr_target, invert=invert_qr, quiet_zone=2)

    width = 72
    border_top = "┌" + "─" * (width - 2) + "┐"
    border_mid = "├" + "─" * (width - 2) + "┤"
    border_bot = "└" + "─" * (width - 2) + "┘"

    def pad_line(text: str) -> str:
        # Pad line to exact inside width
        content_len = len(text)
        space = max(0, width - 4 - content_len)
        return f"│ {text}{' ' * space} │"

    lines = [
        border_top,
        pad_line("DISTRIBUTED MATRIX MULTIPLY — OPERATOR DASHBOARD"),
        pad_line("High-Performance Verifiable Compute Node"),
        border_mid,
        pad_line("NODE IDENTITY & NETWORK STATUS"),
        pad_line(f"Status:        ONLINE (Ready for Tile Tasks)"),
        pad_line(f"Network Mode:  {nat_mode} (Zero Inbound Ports)"),
        pad_line(f"Staking Tier:  {tier} (Auto-Bond Sweep: Active)"),
        pad_line(f"Identity:      {npub}"),
        border_mid,
        pad_line("COMPUTE HARDWARE PROFILE"),
        pad_line(f"Vendor:        {hardware.vendor}"),
        pad_line(f"Device:        {hardware.model}"),
        pad_line(f"VRAM:          {hardware.vram_mb} MB"),
        pad_line(f"Peak Compute:  {hardware.tflops:.1f} TFLOPS (FP32)"),
        pad_line(f"Enclave TEE:   {hardware.tee_type or 'None (Standard Execution)'}"),
        pad_line(f"Acceleration:  {'GPU Accelerated' if hardware.is_gpu else 'CPU Core Pipeline'}"),
        border_mid,
        pad_line("LIGHTNING NETWORK PAYOUT DESTINATION"),
        pad_line(f"Payout Target: {payout_address or '[Scan QR Code below to configure payout]'}")
    ]

    # Embed QR Code centered
    lines.append(pad_line("Scan QR Code with Lightning Wallet (Phoenix / Zeus / CashApp / Blink):"))
    lines.append("│" + " " * (width - 2) + "│")
    for qr_row in qr_text.splitlines():
        # Center QR code
        qr_len = len(qr_row)
        left_pad = max(0, (width - 2 - qr_len) // 2)
        right_pad = max(0, width - 2 - qr_len - left_pad)
        lines.append(f"│{' ' * left_pad}{qr_row}{' ' * right_pad}│")
    lines.append("│" + " " * (width - 2) + "│")
    lines.append(border_bot)

    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Worker Onboarding & Operator Tooling")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-commands")

    # 1. probe
    probe_parser = subparsers.add_parser("probe", help="Detect compute hardware & TEE profiles")
    probe_parser.add_argument("--mock", choices=["nvidia", "rocm", "sev-snp", "tdx", "cpu"], help="Mock profile")

    # 2. keygen
    keygen_parser = subparsers.add_parser("keygen", help="Generate Nostr Secp256k1 keypair")
    keygen_parser.add_argument("--privkey-hex", type=str, help="Existing 32-byte private key hex (optional)")
    keygen_parser.add_argument("--output", "-o", type=str, help="Path to write worker.env file")
    keygen_parser.add_argument("--payout-address", type=str, default="", help="Payout address to write into env file")

    # 3. dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Render ANSI/Unicode operator dashboard")
    dash_parser.add_argument("--payout", "--payout-address", type=str, default="worker@matrix-compute.com", help="Payout address")
    dash_parser.add_argument("--npub", type=str, default="npub1matrixcomputeoperator00000000000000000000000000000000000", help="Nostr npub")
    dash_parser.add_argument("--nat-mode", type=str, default="OUTBOUND-ONLY NAT", help="Network mode string")
    dash_parser.add_argument("--tier", type=str, default="PROBATIONARY", help="Staking tier string")
    dash_parser.add_argument("--mock", choices=["nvidia", "rocm", "sev-snp", "tdx", "cpu"], help="Mock hardware profile")
    dash_parser.add_argument("--invert-qr", action="store_true", help="Invert QR code polarity")

    args = parser.parse_args()

    if args.command == "probe":
        profile = detect_hardware(mock_env=args.mock)
        print(profile.to_json())

    elif args.command == "keygen":
        keypair = generate_keypair(privkey_hex=args.privkey_hex)
        if args.output:
            write_env_file(args.output, keypair, payout_addr=args.payout_address)
        print(json.dumps(keypair, indent=2))

    elif args.command == "dashboard":
        hardware = detect_hardware(mock_env=args.mock)
        dash = render_dashboard(
            payout_address=args.payout,
            npub=args.npub,
            hardware=hardware,
            nat_mode=args.nat_mode,
            tier=args.tier,
            invert_qr=args.invert_qr,
        )
        print(dash)


if __name__ == "__main__":
    main()
