#!/usr/bin/env python3
"""Build patched archives (and EBOOT) from the pristine extract + worksheets.

Layout:
  WORK/pristine/USRDIR/PSARC/<Archive>.psarc.sdat   original wrappers
  WORK/pristine/USRDIR/EBOOT.elf                    decrypted original
  WORK/dec/<Archive>.psarc                          decrypted archives
  WORK/ext/<Archive>/...                            extracted files
  REPO/worksheets/<Archive>/<path inside archive>.json
  REPO/worksheets/EBOOT.elf.json
  OUT/tree/<Archive>/<path>                         patched files only
  OUT/USRDIR/PSARC/<Archive>.psarc.sdat             deployable output
  OUT/USRDIR/EBOOT.elf (+ EBOOT.BIN copy)

Each worksheet is the JSON written by the matching tool's `extract`
command; its "format" field picks the tool. A worksheet whose every "en"
is empty is skipped (nothing to patch). Archives without any patched file
are not rebuilt. A no-op build therefore produces no output files.

Usage:
  build.py [--work WORK] [--out OUT] [--only Logic,Battle] [--check-only]
"""
import json
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_WORK = r"C:\Users\antho\srw2og-work"
PY = sys.executable

TOOL_FOR_FORMAT = {
    "LDBI": "script.py", "LOGO": "script.py", "FIXH": "fixh.py", "BMD": "battle.py",
    "CSB": "csb.py", "WTD": "wtd.py", "ELF": "eboot_strings.py",
}
ARCHIVES = ["Logic", "Common", "General2d", "General3d", "Battle"]


def run(args):
    r = subprocess.run([PY, "-I"] + args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError("%s failed:\n%s%s" % (" ".join(args), r.stdout, r.stderr))
    return r.stdout


def worksheet_has_edits(ws):
    return any(e.get("en") for e in ws.get("strings", []))


def find_worksheets(ws_root):
    """Yield (archive or 'EBOOT', relpath inside archive, json path)."""
    for root, _, files in os.walk(ws_root):
        for f in files:
            if not f.endswith(".json"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, ws_root).replace("\\", "/")
            if rel == "EBOOT.elf.json":
                yield "EBOOT", "EBOOT.elf", full
            else:
                archive, inner = rel.split("/", 1)
                yield archive, inner[:-5], full


def build(work, out, only=None, check_only=False):
    ws_root = os.path.join(REPO, "worksheets")
    tree = os.path.join(out, "tree")
    touched = {}
    problems = 0
    for archive, inner, jpath in sorted(find_worksheets(ws_root)):
        if only and archive not in only:
            continue
        ws = json.load(open(jpath, encoding="utf-8"))
        if not worksheet_has_edits(ws):
            continue
        tool = TOOL_FOR_FORMAT.get(ws.get("format"))
        if tool is None:
            print("!! %s: unknown format %r" % (jpath, ws.get("format")))
            problems += 1
            continue
        if archive == "EBOOT":
            orig = os.path.join(work, "pristine", "USRDIR", "EBOOT.elf")
            dst = os.path.join(out, "USRDIR", "EBOOT.elf")
        else:
            orig = os.path.join(work, "ext", archive, *inner.split("/"))
            dst = os.path.join(tree, archive, *inner.split("/"))
        if check_only:
            print("would build %s/%s" % (archive, inner))
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            run([os.path.join(HERE, tool), "build", orig, jpath, dst])
        except RuntimeError as e:
            print("!! %s" % e)
            problems += 1
            continue
        touched.setdefault(archive, []).append(inner)
        print("built %s/%s" % (archive, inner))
    if check_only:
        return problems == 0
    for archive in ARCHIVES:
        if archive not in touched:
            continue
        template = os.path.join(work, "dec", archive + ".psarc")
        base = os.path.join(work, "ext", archive)
        psarc_out = os.path.join(out, archive + ".psarc")
        sdat_template = os.path.join(work, "pristine", "USRDIR", "PSARC", archive + ".psarc.sdat")
        sdat_out = os.path.join(out, "USRDIR", "PSARC", archive + ".psarc.sdat")
        os.makedirs(os.path.dirname(sdat_out), exist_ok=True)
        print("packing %s (%d patched files)..." % (archive, len(touched[archive])))
        run([os.path.join(HERE, "psarc.py"), "pack", template, os.path.join(tree, archive), psarc_out, base])
        print("encrypting %s..." % archive)
        print(run([os.path.join(HERE, "sdat.py"), "encrypt", sdat_template, psarc_out, sdat_out]).strip())
    if "EBOOT" in touched:
        shutil.copy2(os.path.join(out, "USRDIR", "EBOOT.elf"), os.path.join(out, "USRDIR", "EBOOT.BIN"))
        print("EBOOT.elf copied as EBOOT.BIN (RPCS3 loads a plain ELF)")
    print("done: %d archive(s), %d problem(s)" % (len([a for a in touched if a != "EBOOT"]), problems))
    return problems == 0


def main(argv):
    work = DEFAULT_WORK
    out = os.path.join(REPO, "build")
    only = None
    check_only = "--check-only" in argv
    if "--work" in argv:
        work = argv[argv.index("--work") + 1]
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    return 0 if build(work, out, only, check_only) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
