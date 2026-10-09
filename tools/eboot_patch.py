#!/usr/bin/env python3
"""Patch the decrypted EBOOT.elf so text uses the font's per-glyph advance.

Usage:
  eboot_patch.py IN.elf OUT.elf [--variant advance|flag]

IN is never modified. Every site is checked against the original instruction
word before anything is written; any mismatch aborts without writing OUT.

The game has two layout modes, chosen per draw by a byte in the font object
(font+0xD4, see docs/eboot-renderer.md):

  fixed (flag 0):        each glyph is centred in a size_w-wide cell and the
                         pen advances size_w (32 px for dialogue).
  proportional (flag 1): pen advances size_w/cell_w * entry.advance, and the
                         FTTF page-remap table is applied (U+30xx kana use the
                         narrow page A0, U+FFxx full-width forms use ASCII).

Variants:
  advance (default)  Keep the mode flag, but make the fixed mode advance by
                     size_w/cell_w * entry.advance and drop the centring.
                     16 instruction words in 6 functions (2 draw routines,
                     4 measure routines). No page remap, so Japanese text
                     that is left untranslated keeps its full-width glyphs.
  flag               Alternative: force the flag to 1 in all 6 routines
                     (6 words). Uses the game's own proportional mode, which
                     also remaps kana and full-width forms (see above).

Apply to the EBOOT.elf produced by build.py (string patches only touch data,
these patches only touch .text, so the order does not matter).
"""
import argparse
import os
import struct
import sys

NOP = 0x60000000

# (virtual address, original word, new word, description)
ADVANCE = [
    # Draw routine used for tagged text (0x00A123F0; called via 0x005CE174
    # from the '<'-tag layout 0x005D2120). Fixed-mode loop.
    (0x00A13AD8, 0x7F692050, 0x7D3B4B78,
     "draw A: subf r27,r9,r4 -> mr r27,r9 (convert advance, not cell_w-advance)"),
    (0x00A13B1C, 0xECDB307A, 0xEF9B0232,
     "draw A: fmadds f6,f27,f1,f6 -> fmuls f28,f27,f8 (no centring; f28 = scale*advance)"),
    (0x00A13BC0, 0xC39F002C, NOP,
     "draw A: lfs f28,0x2C(r31) -> nop (squeezed step keeps scale*advance)"),
    (0x00A13BE4, 0xEF8D0732, NOP,
     "draw A: fmuls f28,f13,f28 -> nop (squeezed step keeps scale*advance)"),
    (0x00A13E58, 0xEFDE002A, 0xEFDEE02A,
     "draw A: fadds f30,f30,f0 -> fadds f30,f30,f28 (pen += scale*advance)"),
    (0x00A14970, 0xEFDE302A, 0xEFDEE02A,
     "draw A (outlined pass): fadds f30,f30,f6 -> fadds f30,f30,f28"),
    # Draw routine used for plain text (0x00A149E4; called via 0x005CE1A0 /
    # 0x005CEB3C). Same code with scale in f28 and the step in f27.
    (0x00A15FFC, 0x7D49D850, 0x7D2A4B78,
     "draw B: subf r10,r9,r27 -> mr r10,r9"),
    (0x00A16040, 0xECDC307A, 0xEF7C0232,
     "draw B: fmadds f6,f28,f1,f6 -> fmuls f27,f28,f8"),
    (0x00A160E4, 0xC37F002C, NOP,
     "draw B: lfs f27,0x2C(r31) -> nop"),
    (0x00A16108, 0xEF6D06F2, NOP,
     "draw B: fmuls f27,f13,f27 -> nop"),
    (0x00A1637C, 0xEFDE002A, 0xEFDED82A,
     "draw B: fadds f30,f30,f0 -> fadds f30,f30,f27"),
    (0x00A16E94, 0xEFDE302A, 0xEFDED82A,
     "draw B (outlined pass): fadds f30,f30,f6 -> fadds f30,f30,f27"),
    # Width-measure routines: take the proportional width branch always.
    # (The flag still gates the page remap, which runs earlier.)
    (0x00A11E60, 0x419E0084, NOP,
     "measure 0x00A11CB8: beq cr7 (fixed width) -> nop"),
    (0x00A120D0, 0x419E0064, NOP,
     "measure 0x00A11F28: beq cr7 (fixed width) -> nop"),
    (0x00A12328, 0x4182006C, NOP,
     "measure 0x00A12190: beq (fixed width) -> nop"),
    (0x00A1714C, 0x4186007C, NOP,
     "measure 0x00A16F94: beq cr1 (fixed width) -> nop"),
]

FLAG = [
    (0x00A11D2C, 0x898300D4, 0x39800001, "measure 0x00A11CB8: lbz r12,0xD4(r3) -> li r12,1"),
    (0x00A11F9C, 0x88C300D4, 0x38C00001, "measure 0x00A11F28: lbz r6,0xD4(r3) -> li r6,1"),
    (0x00A121F4, 0x88C300D4, 0x38C00001, "measure 0x00A12190: lbz r6,0xD4(r3) -> li r6,1"),
    (0x00A126F8, 0x881F00D4, 0x38000001, "draw A 0x00A123F0: lbz r0,0xD4(r31) -> li r0,1"),
    (0x00A14CCC, 0x8BDF00D4, 0x3BC00001, "draw B 0x00A149E4: lbz r30,0xD4(r31) -> li r30,1"),
    (0x00A17018, 0x88A300D4, 0x38A00001, "measure 0x00A16F94: lbz r5,0xD4(r3) -> li r5,1"),
]

VARIANTS = {"advance": ADVANCE, "flag": FLAG}


def load_segments(elf):
    if elf[:4] != b"\x7fELF" or elf[4] != 2 or elf[5] != 2:
        raise SystemExit("error: not a big-endian ELF64 file")
    phoff = struct.unpack_from(">Q", elf, 0x20)[0]
    phentsize, phnum = struct.unpack_from(">HH", elf, 0x36)
    segs = []
    for i in range(phnum):
        p = phoff + i * phentsize
        p_type, p_flags = struct.unpack_from(">II", elf, p)
        p_offset, p_vaddr, _paddr, p_filesz = struct.unpack_from(">QQQQ", elf, p + 8)
        if p_type == 1 and p_filesz:
            segs.append((p_vaddr, p_offset, p_filesz, p_flags))
    return segs


def va_to_offset(segs, va):
    for vaddr, offset, filesz, flags in segs:
        if vaddr <= va and va + 4 <= vaddr + filesz:
            if not flags & 1:
                raise SystemExit("error: 0x%08X is not in an executable segment" % va)
            return offset + (va - vaddr)
    raise SystemExit("error: 0x%08X is not inside any PT_LOAD segment" % va)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp", metavar="IN")
    ap.add_argument("out", metavar="OUT")
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="advance")
    args = ap.parse_args()

    if os.path.abspath(args.inp) == os.path.abspath(args.out):
        raise SystemExit("error: OUT must differ from IN (IN is never modified)")

    with open(args.inp, "rb") as f:
        elf = bytearray(f.read())
    segs = load_segments(elf)
    patches = VARIANTS[args.variant]

    # Check every site first; write nothing unless all match.
    plan = []
    bad = 0
    for va, old, new, desc in patches:
        off = va_to_offset(segs, va)
        cur = struct.unpack_from(">I", elf, off)[0]
        if cur != old:
            state = "already patched" if cur == new else "unexpected"
            print("MISMATCH va 0x%08X off 0x%06X: found %08X, expected %08X (%s)"
                  % (va, off, cur, old, state), file=sys.stderr)
            bad += 1
        plan.append((va, off, old, new, desc))
    if bad:
        raise SystemExit("error: %d site(s) did not match the original EBOOT; nothing written" % bad)

    for va, off, old, new, desc in plan:
        struct.pack_into(">I", elf, off, new)
        print("va 0x%08X  off 0x%06X  %08X -> %08X  %s" % (va, off, old, new, desc))

    with open(args.out, "wb") as f:
        f.write(elf)
    print("%s: %d word(s) patched (variant %s) -> %s"
          % (os.path.basename(args.inp), len(plan), args.variant, args.out))


if __name__ == "__main__":
    main()
