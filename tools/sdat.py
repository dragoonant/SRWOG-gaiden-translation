#!/usr/bin/env python3
"""SDAT (licence-free NPDRM EDATA) decrypt / encrypt / verify.

Format (all big-endian), as confirmed on the five BLJS10133 PSARC wrappers:

  0x000  NPD header (0x80): "NPD\\0", version=4, license=0, type=0,
         content_id[0x30] (zero), digest[0x10] @0x40, title_hash[0x10] @0x50,
         dev_hash[0x10] @0x60, activate/expire times (zero).
  0x080  EDAT header (0x10): flags (u32), block_size (u32), file_size (u64).
         flags = 0x0100003C: SDAT | 0x20 (metadata precedes each block)
                 | 0x10 (double-encrypted hash key) | 0x08 (encrypted key)
                 | 0x04 (unused by RPCS3).  Not compressed.
  0x090  metadata-section CMAC (0x10), 0x0A0 header CMAC (0x10),
         0x0B0 metadata ECDSA sig (0x28), 0x0D8 header ECDSA sig (0x28).
  0x100  blocks: for each block i:  0x20 metadata + ciphertext.
         metadata[0:16]  = HMAC-SHA1[0:16] XOR metadata[16:32]
         metadata[16:20] = HMAC-SHA1[16:20]
         metadata[20:32] = random mask bytes (only used by the XOR above)
         ciphertext length = block_size, except the last block which is
         file_size % block_size rounded up to 16.

Per block i:
  sdat_key   = dev_hash XOR SDAT_KEY
  block_key  = dev_hash[0:12] + u32be(i)
  k1         = AES-128-ECB(sdat_key).encrypt(block_key)
  k2         = AES-128-ECB(sdat_key).encrypt(k1)           (flag 0x10)
  data_key   = AES-128-CBC(EDAT_KEY_1, iv=0).decrypt(k1)   (flag 0x08, v4)
  hmac_key   = AES-128-CBC(EDAT_KEY_1, iv=0).decrypt(k2) + 4 zero bytes
  plaintext  = AES-128-CBC(data_key, iv=npd.digest).decrypt(ciphertext)
  HMAC-SHA1(hmac_key, ciphertext) must equal the 20 bytes recovered above.

Header CMACs (RPCS3 does not check these, but we keep them valid):
  cmac_key = AES-128-CBC(EDAT_KEY_1, iv=0).decrypt(sdat_key)
  @0xA0 = AES-CMAC(cmac_key, file[0:0xA0])
  @0x90 = AES-CMAC(cmac_key, concat of every block's 0x20 metadata)
The ECDSA signatures cannot be regenerated (private key unknown) and are
left as-is; RPCS3 never checks them.

Usage:
  sdat.py info    FILE.sdat
  sdat.py verify  FILE.sdat
  sdat.py decrypt FILE.sdat OUT.bin
  sdat.py encrypt TEMPLATE.sdat IN.bin OUT.sdat
      TEMPLATE supplies the NPD header, digest/dev_hash and the per-block
      mask bytes so an unchanged payload re-encrypts byte-identically.
"""
import hmac
import hashlib
import os
import struct
import sys

from Crypto.Cipher import AES
from Crypto.Hash import CMAC

SDAT_KEY = bytes.fromhex("0D655EF8E674A98AB8505CFA7D012933")
EDAT_KEY_0 = bytes.fromhex("BE959CA8308DEFA2E5E180C63712A9AE")
EDAT_KEY_1 = bytes.fromhex("4CA9C14B01C95309969BEC68AA0BC081")
EDAT_IV = bytes(16)

SDAT_FLAG = 0x01000000
F_COMPRESSED = 0x01
F_NOCRYPT = 0x02
F_ENCKEY = 0x08
F_DOUBLEHASH = 0x10
F_META_BEFORE = 0x20
F_DEBUG = 0x80000000

DATA_START = 0x100


class SdatError(Exception):
    pass


class Header:
    def __init__(self, raw: bytes):
        if raw[:4] != b"NPD\0":
            raise SdatError("not an NPD/SDAT file")
        self.raw = bytes(raw[:DATA_START])
        (self.version, self.license, self.type) = struct.unpack_from(">iii", raw, 4)
        self.content_id = raw[0x10:0x40]
        self.digest = raw[0x40:0x50]
        self.title_hash = raw[0x50:0x60]
        self.dev_hash = raw[0x60:0x70]
        (self.flags, self.block_size, self.file_size) = struct.unpack_from(">IIQ", raw, 0x80)
        self.meta_cmac = raw[0x90:0xA0]
        self.header_cmac = raw[0xA0:0xB0]
        self.check_supported()

    def check_supported(self):
        f = self.flags
        if not (f & SDAT_FLAG):
            raise SdatError("not an SDAT (licensed EDAT needs a klicensee)")
        if f & (F_COMPRESSED | F_NOCRYPT | F_DEBUG):
            raise SdatError("unsupported flags 0x%08X (compressed/plain/debug)" % f)
        if not (f & F_META_BEFORE) or not (f & F_ENCKEY) or not (f & F_DOUBLEHASH):
            raise SdatError("unsupported flag layout 0x%08X; tool handles 0x3C-style only" % f)
        if self.version < 2:
            raise SdatError("NPD version %d not supported" % self.version)
        if self.block_size == 0:
            raise SdatError("zero block size")

    @property
    def sdat_key(self) -> bytes:
        return bytes(a ^ b for a, b in zip(self.dev_hash, SDAT_KEY))

    @property
    def edat_key(self) -> bytes:
        return EDAT_KEY_1 if self.version == 4 else EDAT_KEY_0

    @property
    def num_blocks(self) -> int:
        return (self.file_size + self.block_size - 1) // self.block_size

    def block_plain_len(self, i: int) -> int:
        if i == self.num_blocks - 1 and self.file_size % self.block_size:
            return self.file_size % self.block_size
        return self.block_size

    def block_cipher_len(self, i: int) -> int:
        return (self.block_plain_len(i) + 15) & ~15

    def block_offset(self, i: int) -> int:
        # Every block except the last is full size, so this is O(1).
        return DATA_START + i * (0x20 + self.block_size)

    def block_keys(self, i: int):
        ecb = AES.new(self.sdat_key, AES.MODE_ECB)
        block_key = self.dev_hash[:12] + struct.pack(">I", i)
        k1 = ecb.encrypt(block_key)
        k2 = ecb.encrypt(k1)
        data_key = AES.new(self.edat_key, AES.MODE_CBC, iv=EDAT_IV).decrypt(k1)
        hmac_key = AES.new(self.edat_key, AES.MODE_CBC, iv=EDAT_IV).decrypt(k2) + bytes(4)
        return data_key, hmac_key

    def cmac_key(self) -> bytes:
        return AES.new(self.edat_key, AES.MODE_CBC, iv=EDAT_IV).decrypt(self.sdat_key)

    def describe(self) -> str:
        return (
            "NPD v%d license=%d type=%d flags=0x%08X block=0x%X size=%d blocks=%d\n"
            "digest=%s\ndev_hash=%s" % (
                self.version, self.license, self.type, self.flags, self.block_size,
                self.file_size, self.num_blocks, self.digest.hex(), self.dev_hash.hex())
        )


def _cmac(key: bytes, data: bytes) -> bytes:
    c = CMAC.new(key, ciphermod=AES)
    c.update(data)
    return c.digest()


def _unmask(meta: bytes) -> bytes:
    """Recover the 20-byte HMAC from a 0x20 metadata record."""
    return bytes(meta[j] ^ meta[j + 16] for j in range(16)) + meta[16:20]


def _mask(hmac20: bytes, mask: bytes) -> bytes:
    """Build a 0x20 metadata record from a 20-byte HMAC and 16 mask bytes.

    mask[0:4] end up at meta[16:20] but are overwritten by hmac[16:20];
    only mask[4:16] survive verbatim and mask[0:4] are irrelevant.
    """
    out = bytearray(32)
    out[16:32] = mask
    out[16:20] = hmac20[16:20]
    for j in range(16):
        out[j] = hmac20[j] ^ out[16 + j]
    return bytes(out)


def read_header(path: str) -> Header:
    with open(path, "rb") as f:
        return Header(f.read(DATA_START))


def iter_blocks(path: str, h: Header, verify: bool = True):
    """Yield (index, plaintext_padded, metadata) for every block."""
    with open(path, "rb") as f:
        for i in range(h.num_blocks):
            f.seek(h.block_offset(i))
            meta = f.read(0x20)
            clen = h.block_cipher_len(i)
            ct = f.read(clen)
            if len(meta) != 0x20 or len(ct) != clen:
                raise SdatError("truncated at block %d" % i)
            data_key, hmac_key = h.block_keys(i)
            if verify:
                want = _unmask(meta)
                got = hmac.new(hmac_key, ct, hashlib.sha1).digest()
                if not hmac.compare_digest(want, got):
                    raise SdatError("block %d (offset 0x%X): HMAC mismatch" % (i, h.block_offset(i)))
            pt = AES.new(data_key, AES.MODE_CBC, iv=h.digest).decrypt(ct)
            yield i, pt, meta


def verify(path: str, verbose: bool = True) -> bool:
    h = read_header(path)
    size = os.path.getsize(path)
    expected_end = h.block_offset(h.num_blocks - 1) + 0x20 + h.block_cipher_len(h.num_blocks - 1)
    ok = True
    if size < expected_end:
        print("file too short: %d < %d" % (size, expected_end))
        return False
    metas = []
    try:
        for i, _pt, meta in iter_blocks(path, h, verify=True):
            metas.append(meta)
    except SdatError as e:
        print("FAIL:", e)
        return False
    ck = h.cmac_key()
    hc = _cmac(ck, h.raw[:0xA0])
    mc = _cmac(ck, b"".join(metas))
    if hc != h.header_cmac:
        print("header CMAC mismatch (RPCS3 ignores this)")
        ok = False
    if mc != h.meta_cmac:
        print("metadata CMAC mismatch (RPCS3 ignores this)")
        ok = False
    if verbose:
        print("%s: %d blocks, all HMACs valid, header CMAC %s, metadata CMAC %s, trailing bytes %d" % (
            os.path.basename(path), h.num_blocks, "ok" if hc == h.header_cmac else "BAD",
            "ok" if mc == h.meta_cmac else "BAD", size - expected_end))
    return ok


def decrypt(src: str, dst: str, verify_blocks: bool = True) -> Header:
    h = read_header(src)
    with open(dst, "wb") as out:
        for i, pt, _meta in iter_blocks(src, h, verify=verify_blocks):
            out.write(pt[:h.block_plain_len(i)])
    return h


def read_masks(template: str) -> list:
    """Collect the 16 mask bytes of every block in the template file."""
    h = read_header(template)
    masks = []
    with open(template, "rb") as f:
        for i in range(h.num_blocks):
            f.seek(h.block_offset(i))
            masks.append(f.read(0x20)[16:32])
    return masks


def read_pad_tail(template: str) -> bytes:
    """Plaintext padding bytes after file_size in the template's last block
    (needed for a byte-identical re-encrypt of an unchanged payload)."""
    h = read_header(template)
    last = h.num_blocks - 1
    for i, pt, _ in iter_blocks(template, h, verify=False):
        if i == last:
            return pt[h.block_plain_len(i):h.block_cipher_len(i)]
    return b""


def encrypt(template: str, src: str, dst: str, pad_tail: bytes = None) -> None:
    th = read_header(template)
    masks = read_masks(template)
    file_size = os.path.getsize(src)
    hdr = bytearray(th.raw)
    struct.pack_into(">Q", hdr, 0x88, file_size)
    h = Header(bytes(hdr))
    if pad_tail is None:
        pad_tail = read_pad_tail(template) if file_size == th.file_size else b""
    trailing = b""
    with open(template, "rb") as tf:
        tf.seek(th.block_offset(th.num_blocks - 1) + 0x20 + th.block_cipher_len(th.num_blocks - 1))
        trailing = tf.read()
    metas = []
    with open(src, "rb") as f, open(dst, "wb") as out:
        out.write(bytes(hdr))
        for i in range(h.num_blocks):
            plen = h.block_plain_len(i)
            clen = h.block_cipher_len(i)
            pt = f.read(plen)
            if len(pt) != plen:
                raise SdatError("short read on input at block %d" % i)
            if clen != plen:
                pad = (pad_tail + bytes(16))[:clen - plen]
                pt += pad
            data_key, hmac_key = h.block_keys(i)
            ct = AES.new(data_key, AES.MODE_CBC, iv=h.digest).encrypt(pt)
            mac = hmac.new(hmac_key, ct, hashlib.sha1).digest()
            mask = masks[i] if i < len(masks) else os.urandom(16)
            meta = _mask(mac, mask)
            metas.append(meta)
            out.write(meta)
            out.write(ct)
        out.write(trailing)
    # Fix up the two CMACs in the header.
    ck = h.cmac_key()
    hdr[0x90:0xA0] = _cmac(ck, b"".join(metas))      # metadata CMAC first,
    hdr[0xA0:0xB0] = _cmac(ck, bytes(hdr[:0xA0]))    # header CMAC covers it
    with open(dst, "r+b") as out:
        out.seek(0)
        out.write(bytes(hdr))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "info":
        print(read_header(argv[2]).describe())
    elif cmd == "verify":
        return 0 if verify(argv[2]) else 1
    elif cmd == "decrypt":
        h = decrypt(argv[2], argv[3])
        print("wrote %s (%d bytes, %d blocks verified)" % (argv[3], h.file_size, h.num_blocks))
    elif cmd == "encrypt":
        encrypt(argv[2], argv[3], argv[4])
        print("wrote", argv[4])
        return 0 if verify(argv[4]) else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
