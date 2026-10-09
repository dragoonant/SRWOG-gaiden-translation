#!/usr/bin/env python3
"""Copy a build into an RPCS3 install, and roll it back.

How the game handles its data (confirmed on BLJS10133 in RPCS3):
on first boot it copies the five .psarc.sdat archives from the disc folder
to dev_hdd0/game/BLJS10133/USRDIR/PSARC ("game data install") and from then
on reads that copy. If the two copies disagree it shows
「ゲームデータが壊れています」 and refuses to start. Patching both copies in
place also triggers the message. What works: put the patched archives in
the disc folder only, delete dev_hdd0/game/BLJS10133, boot, and confirm the
install prompt. The game then installs the patched archives.

The installed folder holds nothing but copies of disc files plus
PARAM.SFO/ICON0.PNG; save data lives in dev_hdd0/home, so deleting it is
safe. Rollback copies the pristine files back and wipes the installed
copy the same way.

Usage:
  deploy.py install BUILD_DIR   BUILD_DIR/USRDIR/{EBOOT.BIN, PSARC/*.psarc.sdat}
  deploy.py rollback            restore every pristine file
  deploy.py status              show which disc files differ from pristine
Options: --rpcs3 DIR (default C:\\Users\\antho\\RPCS3)
         --pristine DIR (default C:\\Users\\antho\\srw2og-work\\pristine\\USRDIR)
After install or rollback: boot the game and confirm the install prompt
(Cross on that system dialog; the game's own menus use Circle).
"""
import filecmp
import os
import shutil
import sys

SERIAL = "BLJS10133"
DEFAULT_RPCS3 = r"C:\Users\antho\RPCS3"
DEFAULT_PRISTINE = r"C:\Users\antho\srw2og-work\pristine\USRDIR"
ARCHIVES = ["Logic", "Common", "General2d", "General3d", "Battle"]


def disc_usrdir(rpcs3):
    return os.path.join(rpcs3, "dev_hdd0", "disc", SERIAL, "PS3_GAME", "USRDIR")


def wipe_installed(rpcs3):
    gd = os.path.join(rpcs3, "dev_hdd0", "game", SERIAL)
    if os.path.isdir(gd):
        shutil.rmtree(gd)
        print("  removed installed game data %s (the game reinstalls it on boot)" % gd)


def install(build_dir, rpcs3):
    disc = disc_usrdir(rpcs3)
    usrdir = os.path.join(build_dir, "USRDIR")
    n = 0
    eboot = os.path.join(usrdir, "EBOOT.BIN")
    if os.path.exists(eboot):
        shutil.copy2(eboot, os.path.join(disc, "EBOOT.BIN"))
        print("  installed EBOOT.BIN")
        n += 1
    psarc_dir = os.path.join(usrdir, "PSARC")
    if os.path.isdir(psarc_dir):
        for f in sorted(os.listdir(psarc_dir)):
            if f.endswith(".psarc.sdat"):
                shutil.copy2(os.path.join(psarc_dir, f), os.path.join(disc, "PSARC", f))
                print("  installed %s" % f)
                n += 1
    if n:
        wipe_installed(rpcs3)
    print("deployed %d file(s)" % n)


def rollback(rpcs3, pristine):
    disc = disc_usrdir(rpcs3)
    n = 0
    for a in ARCHIVES:
        src = os.path.join(pristine, "PSARC", a + ".psarc.sdat")
        dst = os.path.join(disc, "PSARC", a + ".psarc.sdat")
        if not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(src, dst)
            print("  restored %s" % dst)
            n += 1
    src = os.path.join(pristine, "EBOOT.BIN")
    dst = os.path.join(disc, "EBOOT.BIN")
    if not filecmp.cmp(src, dst, shallow=False):
        shutil.copy2(src, dst)
        print("  restored %s" % dst)
        n += 1
    if n:
        wipe_installed(rpcs3)
    print("rolled back %d file(s)" % n)


def status(rpcs3, pristine):
    disc = disc_usrdir(rpcs3)
    pairs = [(os.path.join(pristine, "EBOOT.BIN"), os.path.join(disc, "EBOOT.BIN"))]
    pairs += [(os.path.join(pristine, "PSARC", a + ".psarc.sdat"),
               os.path.join(disc, "PSARC", a + ".psarc.sdat")) for a in ARCHIVES]
    for src, dst in pairs:
        same = filecmp.cmp(src, dst, shallow=False)
        print("  %-9s %s" % ("pristine" if same else "PATCHED", dst))


def main(argv):
    rpcs3, pristine = DEFAULT_RPCS3, DEFAULT_PRISTINE
    for flag in ("--rpcs3", "--pristine"):
        if flag in argv:
            i = argv.index(flag)
            if flag == "--rpcs3":
                rpcs3 = argv[i + 1]
            else:
                pristine = argv[i + 1]
            del argv[i:i + 2]
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "install":
        install(argv[2], rpcs3)
    elif cmd == "rollback":
        rollback(rpcs3, pristine)
    elif cmd == "status":
        status(rpcs3, pristine)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
