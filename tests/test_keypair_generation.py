"""
Unit and integration tests for Nostr Secp256k1 keypair generation, Bech32 encoding, and env file persistence.
"""

import os
import stat
import pytest

from scripts.onboard import (
    generate_keypair,
    bech32_encode,
    bech32_decode,
    write_env_file,
    SECP256K1_ORDER,
)


def test_generate_random_keypair():
    kp = generate_keypair()
    assert "hex_privkey" in kp
    assert "hex_pubkey" in kp
    assert "npub" in kp
    assert "nsec" in kp

    assert len(kp["hex_privkey"]) == 64
    assert len(kp["hex_pubkey"]) == 64
    assert kp["npub"].startswith("npub1")
    assert kp["nsec"].startswith("nsec1")

    # Private key scalar in valid curve range
    priv_int = int(kp["hex_privkey"], 16)
    assert 1 <= priv_int < SECP256K1_ORDER


def test_generate_keypair_from_privkey_hex():
    # Known 32-byte private key (all 1s)
    priv_hex = "01" * 32
    kp1 = generate_keypair(privkey_hex=priv_hex)
    assert kp1["hex_privkey"] == priv_hex

    # Determinism: same private key produces exact same public key, npub, and nsec
    kp2 = generate_keypair(privkey_hex=priv_hex)
    assert kp1["hex_pubkey"] == kp2["hex_pubkey"]
    assert kp1["npub"] == kp2["npub"]
    assert kp1["nsec"] == kp2["nsec"]


def test_invalid_privkey_hex_errors():
    with pytest.raises(ValueError, match="must be 64 characters"):
        generate_keypair(privkey_hex="1234abcd")

    with pytest.raises(ValueError, match="invalid hexadecimal"):
        generate_keypair(privkey_hex="zz" * 32)


def test_bech32_roundtrip_bytes():
    payload = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    encoded = bech32_encode("test", payload)
    assert encoded.startswith("test1")

    hrp, decoded = bech32_decode(encoded)
    assert hrp == "test"
    assert decoded == payload


def test_bech32_tamper_fails_checksum():
    payload = b"verifiable_matrix_compute"
    encoded = bech32_encode("matrix", payload)

    # Flip the last character
    last_char = encoded[-1]
    new_char = "q" if last_char != "q" else "p"
    tampered = encoded[:-1] + new_char

    with pytest.raises(ValueError, match="Invalid Bech32 checksum"):
        bech32_decode(tampered)


def test_keypair_roundtrip_decoding():
    kp = generate_keypair()
    hrp_pub, pub_bytes = bech32_decode(kp["npub"])
    hrp_sec, priv_bytes = bech32_decode(kp["nsec"])

    assert hrp_pub == "npub"
    assert hrp_sec == "nsec"
    assert pub_bytes.hex() == kp["hex_pubkey"]
    assert priv_bytes.hex() == kp["hex_privkey"]


def test_write_env_file_creates_file(tmp_worker_dir):
    target = os.path.join(tmp_worker_dir, ".matrix", "worker.env")
    kp = generate_keypair()
    payout = "sats@matrix-compute.com"

    write_env_file(target, kp, payout_addr=payout)
    assert os.path.isfile(target)

    with open(target, "r", encoding="utf-8") as f:
        content = f.read()

    assert f"MATRIX_WORKER_PRIVKEY={kp['hex_privkey']}" in content
    assert f"MATRIX_WORKER_NPUB={kp['npub']}" in content
    assert f"MATRIX_WORKER_NSEC={kp['nsec']}" in content
    assert f"MATRIX_WORKER_PAYOUT_ADDRESS={payout}" in content
    assert "MATRIX_WORKER_NAT_MODE=reverse_tunnel" in content

    # Verify POSIX permissions (0600)
    if os.name == "posix":
        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o600
