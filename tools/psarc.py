#!/usr/bin/env python3
"""PSARC v1.4 (PlayStation archive) list / extract / repack.

Layout (big-endian), as confirmed on the BLJS10133 archives:

  0x00 "PSAR"  u16 major=1  u16 minor=4  "zlib"
  0x0C u32 toc_length   (header + TOC + block table; first data byte)
  0x10 u32 toc_entry_size (0x1E)
  0x14 u32 toc_entries    (manifest counts as entry 0)
  0x18 u32 block_size     (0x10000)
  0x1C u32 archive_flags  (1 = ignore case, 2 = absolute paths)
  0x20 TOC: per entry  md5(name)[16]  u32 first_block  u40 size  u40 offset
       entry 0 is the manifest: "\n"-separated file names, md5 = zeros.
  then block table: one entry per 64 KB block, width = bytes needed to
       hold block_size (2 for 0x10000); value = stored length, 0 = full
       raw block of block_size bytes.
  then data: each block is either a standalone zlib stream (starts 0x78)
       or raw bytes when stored length == block_size.

Repacking reproduces the original byte-for-byte when the payload is
unchanged: entries keep their order, each block is zlib level 9 with
default window/memory/strategy, a block is stored raw if zlib would not
shrink it, and the data region keeps the same alignment (none).

Usage:
  psarc.py list    ARCHIVE
  psarc.py extract ARCHIVE OUTDIR
  psarc.py pack    TEMPLATE_ARCHIVE INDIR OUT_ARCHIVE
      Names, order and flags come from TEMPLATE; file bodies from INDIR.
  psarc.py check   ARCHIVE           (inflate every block, report stats)
"""
import hashlib
import os
import struct
import sys
import zlib

HEADER_SIZE = 0x20
ZLIB_LEVEL = 9


class PsarcError(Exception):
    pass


class Entry:
    __slots__ = ("name", "md5", "first_block", "size", "offset", "index")

    def __init__(self, index, md5, first_block, size, offset, name=None):
        self.index = index
        self.md5 = md5
        self.first_block = first_block
        self.size = size
        self.offset = offset
        self.name = name


class Psarc:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        hdr = self.f.read(HEADER_SIZE)
        if hdr[:4] != b"PSAR":
            raise PsarcError("not a PSARC")
        self.major, self.minor = struct.unpack_from(">HH", hdr, 4)
        self.compression = hdr[8:12]
        (self.toc_length, self.entry_size, self.num_entries,
         self.block_size, self.flags) = struct.unpack_from(">IIIII", hdr, 12)
        if self.compression != b"zlib" or self.entry_size != 30:
            raise PsarcError("unsupported PSARC variant: %r entry=%d" % (self.compression, self.entry_size))
        self.block_width = 1
        while (1 << (8 * self.block_width)) < self.block_size:
            self.block_width += 1
        self.entries = []
        toc = self.f.read(self.entry_size * self.num_entries)
        for i in range(self.num_entries):
            e = toc[i * 30:(i + 1) * 30]
            md5 = e[:16]
            first_block = struct.unpack(">I", e[16:20])[0]
            size = int.from_bytes(e[20:25], "big")
            offset = int.from_bytes(e[25:30], "big")
            self.entries.append(Entry(i, md5, first_block, size, offset))
        table_bytes = self.toc_length - HEADER_SIZE - self.entry_size * self.num_entries
        self.num_blocks = table_bytes // self.block_width
        raw = self.f.read(table_bytes)
        w = self.block_width
        self.block_sizes = [int.from_bytes(raw[i * w:(i + 1) * w], "big") for i in range(self.num_blocks)]
        names = self.read_entry(self.entries[0]).decode("utf-8").split("\n")
        if len(names) != self.num_entries - 1:
            raise PsarcError("manifest has %d names for %d entries" % (len(names), self.num_entries - 1))
        for e, n in zip(self.entries[1:], names):
            e.name = n
        self.entries[0].name = "<manifest>"

    def close(self):
        self.f.close()

    def stored_len(self, block_index):
        v = self.block_sizes[block_index]
        return self.block_size if v == 0 else v

    def read_block_raw(self, offset, stored):
        self.f.seek(offset)
        d = self.f.read(stored)
        if len(d) != stored:
            raise PsarcError("truncated block at 0x%X" % offset)
        return d

    def iter_entry_blocks(self, e):
        """Yield (block_index, offset, stored_bytes, inflated_bytes)."""
        remaining = e.size
        off = e.offset
        bi = e.first_block
        while remaining > 0:
            stored = self.stored_len(bi)
            raw = self.read_block_raw(off, stored)
            want = min(self.block_size, remaining)
            if stored == self.block_size and not raw.startswith(b"\x78"):
                data = raw
            else:
                try:
                    data = zlib.decompress(raw)
                except zlib.error:
                    data = raw  # raw block that happens to start with 0x78
            if len(data) < want:
                raise PsarcError("%s: block %d inflated to %d, wanted %d" % (e.name, bi, len(data), want))
            yield bi, off, raw, data[:want]
            remaining -= want
            off += stored
            bi += 1

    def read_entry(self, e):
        return b"".join(d for _, _, _, d in self.iter_entry_blocks(e))

    def entry_by_name(self, name):
        for e in self.entries[1:]:
            if e.name == name:
                return e
        raise KeyError(name)


def name_md5(name):
    return hashlib.md5(name.encode("utf-8")).digest()


def cmd_list(path):
    p = Psarc(path)
    print("PSARC v%d.%d %s toc=0x%X entries=%d blocks=%d block=0x%X flags=0x%X" % (
        p.major, p.minor, p.compression.decode(), p.toc_length, p.num_entries - 1,
        p.num_blocks, p.block_size, p.flags))
    for e in p.entries[1:]:
        print("%10d  0x%010X  %s" % (e.size, e.offset, e.name))
    p.close()


def cmd_extract(path, outdir):
    p = Psarc(path)
    n = 0
    for e in p.entries[1:]:
        rel = e.name.lstrip("/").replace("\\", "/")
        dst = os.path.join(outdir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as out:
            for _, _, _, data in p.iter_entry_blocks(e):
                out.write(data)
        if name_md5(e.name) != e.md5:
            print("warning: md5 mismatch for", e.name)
        n += 1
    with open(os.path.join(outdir, ".psarc_manifest"), "w", encoding="utf-8", newline="\n") as m:
        m.write("\n".join(e.name for e in p.entries[1:]))
    print("extracted %d files to %s" % (n, outdir))
    p.close()


def compress_block(data):
    """Return the stored form of one block exactly as the original packer did."""
    if len(data) == 0:
        return b""
    c = zlib.compress(data, ZLIB_LEVEL)
    if len(c) >= len(data):
        return data
    return c


def cmd_pack(template, indir, outpath):
    t = Psarc(template)
    names = [e.name for e in t.entries[1:]]
    manifest = "\n".join(names).encode("utf-8")
    bodies = [manifest]
    for n in names:
        rel = n.lstrip("/").replace("\\", "/")
        src = os.path.join(indir, *rel.split("/"))
        with open(src, "rb") as f:
            bodies.append(f.read())
    bs = t.block_size
    # First pass: compress everything, build block table. Identical file
    # bodies share one block run (the original packer deduplicates).
    block_table = []
    stored_blocks = []
    toc = []          # [md5, first_block, size, run_index]
    runs = []         # run_index -> (first_block, nblocks)
    seen = {}         # sha1(body) -> run_index
    for i, body in enumerate(bodies):
        key = hashlib.sha1(body).digest()
        if i > 0 and key in seen:
            run = seen[key]
        else:
            first_block = len(block_table)
            for pos in range(0, len(body), bs):
                chunk = body[pos:pos + bs]
                s = compress_block(chunk)
                stored_blocks.append(s)
                block_table.append(0 if len(s) == bs else len(s))
            run = len(runs)
            runs.append((first_block, len(block_table) - first_block))
            seen[key] = run
        toc.append([t.entries[i].md5 if i == 0 else name_md5(names[i - 1]), len(body), run])
    w = t.block_width
    toc_length = HEADER_SIZE + 30 * len(toc) + w * len(block_table)
    # Second pass: offsets per run, then TOC.
    run_offsets = []
    off = toc_length
    for first_block, nblocks in runs:
        run_offsets.append(off)
        for b in range(first_block, first_block + nblocks):
            off += len(stored_blocks[b])
    out_toc = bytearray()
    for md5, size, run in toc:
        first_block = runs[run][0]
        out_toc += md5 + struct.pack(">I", first_block) + size.to_bytes(5, "big") + run_offsets[run].to_bytes(5, "big")
    hdr = b"PSAR" + struct.pack(">HH", t.major, t.minor) + b"zlib" + struct.pack(
        ">IIIII", toc_length, 30, len(toc), bs, t.flags)
    with open(outpath, "wb") as o:
        o.write(hdr)
        o.write(out_toc)
        for v in block_table:
            o.write(v.to_bytes(w, "big"))
        for s in stored_blocks:
            o.write(s)
    t.close()
    print("wrote %s: %d entries, %d blocks, %d bytes" % (outpath, len(toc) - 1, len(block_table), off))


def cmd_check(path):
    p = Psarc(path)
    raw_blocks = zlib_blocks = 0
    mismatched = 0
    for e in p.entries:
        for bi, off, raw, data in p.iter_entry_blocks(e):
            if raw is data or (len(raw) == len(data) and raw == data):
                raw_blocks += 1
            else:
                zlib_blocks += 1
                if compress_block(data) != raw:
                    mismatched += 1
    print("%s: %d zlib blocks, %d raw blocks, %d blocks not reproduced by level-%d recompression" % (
        os.path.basename(path), zlib_blocks, raw_blocks, mismatched, ZLIB_LEVEL))
    p.close()
    return mismatched == 0


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        cmd_list(argv[2])
    elif cmd == "extract":
        cmd_extract(argv[2], argv[3])
    elif cmd == "pack":
        cmd_pack(argv[2], argv[3], argv[4])
    elif cmd == "check":
        return 0 if cmd_check(argv[2]) else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
