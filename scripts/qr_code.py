#!/usr/bin/env python3
"""
Zero-Dependency Pure-Python QR Code Generator & Terminal Half-Block Renderer.

Complies with ISO/IEC 18004 specifications:
- Dynamic Version Selection (Versions 1 to 10)
- Byte Mode Encoding (8-bit ASCII / UTF-8)
- Galois Field GF(2^8) arithmetic with generator polynomials
- Reed-Solomon Error Correction (EC Level M / L)
- Standard Alignment, Timing, Finder Patterns & Format Information
- Compact Terminal Output using Unicode Half-Blocks (▀, ▄, █, ' ')
"""

import argparse
import sys
from typing import List, Optional, Tuple

# Galois Field GF(256) with primitive polynomial 0x11d (285)
GF_EXP: List[int] = [0] * 512
GF_LOG: List[int] = [0] * 256

def _init_gf() -> None:
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]

_init_gf()

def gf_mul(x: int, y: int) -> int:
    if x == 0 or y == 0:
        return 0
    return GF_EXP[GF_LOG[x] + GF_LOG[y]]

def gf_poly_mul(p: List[int], q: List[int]) -> List[int]:
    """Multiply polynomials in GF(256)."""
    res = [0] * (len(p) + len(q) - 1)
    for j, q_val in enumerate(q):
        for i, p_val in enumerate(p):
            res[i + j] ^= gf_mul(p_val, q_val)
    return res

def rs_generator_poly(ec_count: int) -> List[int]:
    """Generate Reed-Solomon generator polynomial for ec_count codewords."""
    g = [1]
    for i in range(ec_count):
        g = gf_poly_mul(g, [1, GF_EXP[i]])
    return g

def rs_compute_ec(data: List[int], ec_count: int) -> List[int]:
    """Compute ec_count Reed-Solomon error correction codewords for data bytes."""
    gen = rs_generator_poly(ec_count)
    msg = data + [0] * ec_count
    for i in range(len(data)):
        lead = msg[i]
        if lead != 0:
            for j in range(len(gen)):
                msg[i + j] ^= gf_mul(gen[j], lead)
    return msg[len(data):]


# Version Specifications for EC Level M:
# (total_codewords, data_codewords, ec_per_block, num_blocks_g1, data_per_block_g1, num_blocks_g2, data_per_block_g2)
VERSION_SPECS_M = {
    1:  (26,  16,  10, 1, 16,  0, 0),
    2:  (44,  28,  16, 1, 28,  0, 0),
    3:  (70,  44,  26, 1, 44,  0, 0),
    4:  (100, 64,  18, 2, 32,  0, 0),
    5:  (134, 86,  24, 2, 43,  0, 0),
    6:  (172, 108, 16, 4, 27,  0, 0),
    7:  (196, 124, 18, 4, 31,  0, 0),
    8:  (242, 154, 22, 2, 38,  2, 39),
    9:  (292, 182, 22, 3, 36,  2, 37),
    10: (346, 216, 26, 4, 43,  1, 44),
}

ALIGNMENT_PATTERNS = {
    1:  [],
    2:  [6, 18],
    3:  [6, 22],
    4:  [6, 26],
    5:  [6, 30],
    6:  [6, 34],
    7:  [6, 22, 38],
    8:  [6, 24, 42],
    9:  [6, 26, 46],
    10: [6, 28, 50],
}

# Format information: 15-bit format strings for EC Level M with mask 0..7
# Mask 0 (000), EC Level M (00) -> 00 000 with BCH error correction and XOR 0x5412 -> 101010000010010
FORMAT_INFO_M_MASK0 = 0x5412 ^ 0x0000  # 00000 -> BCH remainder 0000000000 -> 0x0000 ^ 0x5412 = 0x5412

# Version information: 18-bit BCH (18, 6) codes for Versions 7-10 (ISO/IEC 18004 Section 6.5.2 / Table D.1)
# 6 bits version number + 12 bits BCH error correction (generator polynomial 0x1F25)
VERSION_INFO = {
    7: 0x07C94,
    8: 0x085BC,
    9: 0x09A99,
    10: 0x0A4D3,
}



class BitStream:
    """Helper to accumulate bitstream and produce byte arrays."""
    def __init__(self) -> None:
        self.bits: List[int] = []

    def append_bits(self, val: int, length: int) -> None:
        for i in reversed(range(length)):
            self.bits.append((val >> i) & 1)

    def append_bytes(self, data: bytes) -> None:
        for b in data:
            self.append_bits(b, 8)

    def to_bytes(self) -> List[int]:
        out = []
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8]
            byte_val = 0
            for bit in chunk:
                byte_val = (byte_val << 1) | bit
            if len(chunk) < 8:
                byte_val <<= (8 - len(chunk))
            out.append(byte_val)
        return out


def choose_version(data_len: int) -> int:
    """Select smallest QR version (1-10) that can hold data_len bytes in Byte mode."""
    for ver in range(1, 11):
        spec = VERSION_SPECS_M[ver]
        max_data = spec[1]
        # Byte mode header: 4 bits mode + (8 bits length for v1-9, 16 bits for v10)
        hdr_bits = 4 + (16 if ver >= 10 else 8)
        avail_bytes = max_data - ((hdr_bits + 7) // 8)
        if data_len <= avail_bytes:
            return ver
    raise ValueError(f"Payload length {data_len} exceeds max supported QR version 10 capacity")


def encode_data(data: str, version: int) -> List[int]:
    """Encode string in 8-bit byte mode with padding and error correction interleaving."""
    raw_bytes = data.encode("utf-8")
    data_len = len(raw_bytes)
    spec = VERSION_SPECS_M[version]
    total_data_codewords = spec[1]

    bs = BitStream()
    # 1. Mode Indicator: 0100 for Byte Mode
    bs.append_bits(0b0100, 4)

    # 2. Character Count Indicator
    char_count_bits = 16 if version >= 10 else 8
    bs.append_bits(data_len, char_count_bits)

    # 3. Data Bytes
    bs.append_bytes(raw_bytes)

    # 4. Terminator bits: up to 4 zero bits
    bits_needed = total_data_codewords * 8 - len(bs.bits)
    term_bits = min(4, max(0, bits_needed))
    bs.append_bits(0, term_bits)

    # 5. Pad to byte boundary
    pad_bits = (8 - (len(bs.bits) % 8)) % 8
    bs.append_bits(0, pad_bits)

    # 6. Pad bytes (alternating 0xEC and 0x11)
    data_bytes = bs.to_bytes()
    pad_sequence = [0xEC, 0x11]
    pad_idx = 0
    while len(data_bytes) < total_data_codewords:
        data_bytes.append(pad_sequence[pad_idx % 2])
        pad_idx += 1

    # 7. Block splitting and error correction calculation
    ec_per_block = spec[2]
    num_b1, data_b1 = spec[3], spec[4]
    num_b2, data_b2 = spec[5], spec[6]

    blocks_data: List[List[int]] = []
    blocks_ec: List[List[int]] = []
    cursor = 0

    for _ in range(num_b1):
        blk = data_bytes[cursor : cursor + data_b1]
        cursor += data_b1
        blocks_data.append(blk)
        blocks_ec.append(rs_compute_ec(blk, ec_per_block))

    for _ in range(num_b2):
        blk = data_bytes[cursor : cursor + data_b2]
        cursor += data_b2
        blocks_data.append(blk)
        blocks_ec.append(rs_compute_ec(blk, ec_per_block))

    # 8. Interleave data codewords
    interleaved: List[int] = []
    max_data_len = max(len(b) for b in blocks_data)
    for i in range(max_data_len):
        for b in blocks_data:
            if i < len(b):
                interleaved.append(b[i])

    # 9. Interleave error correction codewords
    for i in range(ec_per_block):
        for b in blocks_ec:
            interleaved.append(b[i])

    return interleaved


class QRCodeMatrix:
    """Builds and lays out QR Code 2D module matrix."""
    def __init__(self, version: int) -> None:
        self.version = version
        self.size = 4 * version + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.reserved = [[False] * self.size for _ in range(self.size)]

    def _set_module(self, r: int, c: int, val: bool) -> None:
        self.modules[r][c] = val
        self.reserved[r][c] = True

    def place_finder(self, row: int, col: int) -> None:
        for r in range(-1, 8):
            for c in range(-1, 8):
                nr, nc = row + r, col + c
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    if 0 <= r <= 6 and 0 <= c <= 6:
                        # 7x7 finder pattern
                        is_dark = (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
                        self._set_module(nr, nc, is_dark)
                    else:
                        # Separator light border
                        self._set_module(nr, nc, False)

    def place_timing(self) -> None:
        for i in range(8, self.size - 8):
            val = (i % 2 == 0)
            if not self.reserved[6][i]:
                self._set_module(6, i, val)
            if not self.reserved[i][6]:
                self._set_module(i, 6, val)

    def place_alignment(self) -> None:
        coords = ALIGNMENT_PATTERNS.get(self.version, [])
        for r in coords:
            for c in coords:
                # Do not place alignment patterns overlapping finders
                if (r < 9 and c < 9) or (r < 9 and c >= self.size - 9) or (r >= self.size - 9 and c < 9):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        is_dark = (abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0))
                        self._set_module(r + dr, c + dc, is_dark)

    def reserve_format_info(self) -> None:
        # Top-left horizontal & vertical
        for i in range(9):
            if i != 6:
                self.reserved[8][i] = True
                self.reserved[i][8] = True
        # Top-right horizontal
        for i in range(self.size - 8, self.size):
            self.reserved[8][i] = True
        # Bottom-left vertical
        for i in range(self.size - 8, self.size):
            self.reserved[i][8] = True
        # Dark module
        self._set_module(4 * self.version + 9, 8, True)

        # Version information (Versions 7-10: two 3x6 rectangles)
        if self.version >= 7:
            for i in range(6):
                for j in range(3):
                    self.reserved[i][self.size - 11 + j] = True
                    self.reserved[self.size - 11 + j][i] = True

    def place_data(self, data_bytes: List[int]) -> None:
        bit_idx = 0
        bits: List[int] = []
        for b in data_bytes:
            for i in reversed(range(8)):
                bits.append((b >> i) & 1)

        # Place data bits in 2-column zigzag from right to left
        col = self.size - 1
        going_up = True
        while col > 0:
            if col == 6:
                col -= 1  # Skip timing column

            rows = list(reversed(range(self.size))) if going_up else list(range(self.size))
            for r in rows:
                for c in (col, col - 1):
                    if not self.reserved[r][c]:
                        bit = bits[bit_idx] if bit_idx < len(bits) else 0
                        bit_idx += 1
                        # Apply standard mask pattern 0: (row + col) % 2 == 0
                        mask = ((r + c) % 2 == 0)
                        self.modules[r][c] = bool(bit ^ mask)

            going_up = not going_up
            col -= 2

    def place_format_info(self) -> None:
        # Standard Format bits for EC Level M, Mask 0
        fmt = FORMAT_INFO_M_MASK0
        format_bits = [(fmt >> (14 - i)) & 1 for i in range(15)]

        # Top-left and around finders
        # Horizontal around top-left
        seq1 = [0, 1, 2, 3, 4, 5, 7, 8]
        for idx, col in enumerate(seq1):
            self.modules[8][col] = bool(format_bits[idx])
        # Vertical around top-left
        seq2 = [7, 5, 4, 3, 2, 1, 0]
        for idx, row in enumerate(seq2):
            self.modules[row][8] = bool(format_bits[8 + idx])

        # Bottom-left vertical
        for idx in range(7):
            self.modules[self.size - 1 - idx][8] = bool(format_bits[idx])
        # Top-right horizontal
        for idx in range(8):
            self.modules[8][self.size - 8 + idx] = bool(format_bits[7 + idx])

    def place_version_info(self) -> None:
        """Place 18-bit BCH version information for versions >= 7."""
        if self.version < 7:
            return
        bits = VERSION_INFO.get(self.version)
        if bits is None:
            return
        for i in range(18):
            val = bool((bits >> i) & 1)
            # Top-right 6x3 block: row 0..5, col (size - 11) + (0..2)
            self.modules[i // 3][self.size - 11 + (i % 3)] = val
            # Bottom-left 3x6 block: row (size - 11) + (0..2), col 0..5
            self.modules[self.size - 11 + (i % 3)][i // 3] = val


def generate_qr_matrix(data: str, version: Optional[int] = None) -> List[List[bool]]:
    """Generate 2D boolean module matrix (True = dark module, False = light module)."""
    if not version:
        version = choose_version(len(data.encode("utf-8")))

    codenwords = encode_data(data, version)
    matrix = QRCodeMatrix(version)
    matrix.place_finder(0, 0)
    matrix.place_finder(0, matrix.size - 7)
    matrix.place_finder(matrix.size - 7, 0)
    matrix.place_timing()
    matrix.place_alignment()
    matrix.reserve_format_info()
    matrix.place_data(codenwords)
    matrix.place_format_info()
    matrix.place_version_info()

    return matrix.modules


def render_terminal_qr(data: str, invert: bool = False, quiet_zone: int = 2) -> str:
    """
    Renders QR code to compact terminal string using Unicode half-blocks:
    '▀' (upper half), '▄' (lower half), '█' (full block), ' ' (space).

    Packs 2 vertical modules per character line.
    By default (invert=False), assumes standard dark terminal background (black background, light text):
    Light modules -> foreground blocks; Dark modules -> background spaces.
    With invert=True, dark modules -> foreground blocks.
    """
    modules = generate_qr_matrix(data)
    size = len(modules)

    # Pad matrix with quiet zone
    padded_size = size + 2 * quiet_zone
    padded = [[False] * padded_size for _ in range(padded_size)]
    for r in range(size):
        for c in range(size):
            padded[r + quiet_zone][c + quiet_zone] = modules[r][c]

    lines: List[str] = []
    # Step 2 rows at a time
    for r in range(0, padded_size, 2):
        row_chars: List[str] = []
        for c in range(padded_size):
            top = padded[r][c]
            bot = padded[r + 1][c] if (r + 1 < padded_size) else False

            if not invert:
                # Dark terminal: Light module (False) is rendered as white block
                # top_white is not top, bot_white is not bot
                t_lit = not top
                b_lit = not bot
            else:
                t_lit = top
                b_lit = bot

            if t_lit and b_lit:
                row_chars.append("█")
            elif t_lit and not b_lit:
                row_chars.append("▀")
            elif not t_lit and b_lit:
                row_chars.append("▄")
            else:
                row_chars.append(" ")
        lines.append("".join(row_chars))

    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Zero-Dependency Pure-Python QR Code Terminal Renderer")
    parser.add_argument("data", type=str, help="Text, Lightning Address, or LNURL to encode")
    parser.add_argument("--invert", action="store_true", help="Invert dark/light modules")
    parser.add_argument("--quiet-zone", type=int, default=2, help="Quiet zone border in modules (default: 2)")
    args = parser.parse_args()

    qr_str = render_terminal_qr(args.data, invert=args.invert, quiet_zone=args.quiet_zone)
    print(qr_str)


if __name__ == "__main__":
    main()
