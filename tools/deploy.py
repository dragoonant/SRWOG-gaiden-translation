#!/usr/bin/env python3
"""Copy a build into an RPCS3 install, with backup and rollback.

The game installs the five SDAT archives from the disc folder to
dev_hdd0/game/BLJS10133/USRDIR/PSARC on first boot and then runs from that
copy; at boot it compares the two and shows "game data is corrupted" when
they differ. So a patched archive must land in BOTH places.

Usage:
  deploy.py install BUILD_DIR [--rpcs3 C:\\Users\\antho\\RPCS3]
      BUILD_DIR holds USRDIR/EBOOT.BIN and/or USRDIR/PSARC/*.psarc.sdat.
      Each target file is backed up once as <name>.orig next to it (never
      overwritten if it already exists), then replaced.
  deploy.py rollback [--rpcs3 DIR]
      Restore every <name>.orig in both locations.
  deploy.py status  [--rpcs3 DIR]
      Show which files are currently patched (differ from .orig).
"""
import filecmp
import os
import shutil
import sys

SERIAL = "BLJS10133"
DEFAULT_RPCS3 = r"C:\Users\antho\RPCS3"


def targets(rpcs3):
    disc = os.path.join(rpcs3, "dev_hdd0", "disc", SERIAL, "PS3_GAME", "USRDIR")
    hdd = os.path.join(rpcs3, "dev_hdd0", "game", SERIAL, "USRDIR")
    return disc, hdd


def backup_and_copy(src, dst):
    orig = dst + ".orig"
    if os.path.exists(dst) and not os.path.exists(orig):
        shutil.copy2(dst, orig)
        print("  backed up %s" % dst)
    shutil.copy2(src, dst)
    print("  installed %s (%d bytes)" % (dst, os.path.getsize(dst)))


def install(build_dir, rpcs3):
    disc, hdd = targets(rpcs3)
    usrdir = os.path.join(build_dir, "USRDIR")
    n = 0
    eboot = os.path.join(usrdir, "EBOOT.BIN")
    if os.path.exists(eboot):
        backup_and_copy(eboot, os.path.join(disc, "EBOOT.BIN"))
        n += 1
    psarc_dir = os.path.join(usrdir, "PSARC")
    if os.path.isdir(psarc_dir):
        for f in sorted(os.listdir(psarc_dir)):
            if not f.endswith(".psarc.sdat"):
                continue
            src = os.path.join(psarc_dir, f)
            backup_and_copy(src, os.path.join(disc, "PSARC", f))
            hdd_target = os.path.join(hdd, "PSARC", f)
            if os.path.exists(hdd_target):
                backup_and_copy(src, hdd_target)
            else:
                print("  (no installed copy yet at %s; the game will install from disc)" % hdd_target)
            n += 1
    print("deployed %d file(s)" % n)


def rollback(rpcs3):
    disc, hdd = targets(rpcs3)
    n = 0
    for d in (disc, os.path.join(disc, "PSARC"), os.path.join(hdd, "PSARC")):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".orig"):
                orig = os.path.join(d, f)
                dst = orig[:-5]
                shutil.copy2(orig, dst)
                os.remove(orig)
                print("  restored %s" % dst)
                n += 1
    print("rolled back %d file(s)" % n)


def status(rpcs3):
    disc, hdd = targets(rpcs3)
    for d in (disc, os.path.join(disc, "PSARC"), os.path.join(hdd, "PSARC")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".orig"):
                dst = os.path.join(d, f[:-5])
                same = filecmp.cmp(os.path.join(d, f), dst, shallow=False)
                print("  %-10s %s" % ("pristine" if same else "PATCHED", dst))


def main(argv):
    rpcs3 = DEFAULT_RPCS3
    if "--rpcs3" in argv:
        i = argv.index("--rpcs3")
        rpcs3 = argv[i + 1]
        del argv[i:i + 2]
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "install":
        install(argv[2], rpcs3)
    elif cmd == "rollback":
        rollback(rpcs3)
    elif cmd == "status":
        status(rpcs3)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
