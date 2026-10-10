#!/usr/bin/env python3
"""Copy a build into an RPCS3 install, and roll it back.

How the game checks its data (confirmed on BLJS10133 in RPCS3, 2026-10-09):
on first boot it copies the five .psarc.sdat archives from the disc folder
to dev_hdd0/game/BLJS10133/USRDIR/PSARC and gives each copy the disc file's
modification time. On every later boot it compares size and modification
time (stat) of the two copies and shows 「ゲームデータが壊れています」 if they
differ. Contents are not compared.

The game also writes its own ICON0.PNG into the installed folder, stamped
with Common.psarc.sdat's modification time, and checks that stamp on boot
(found 2026-10-09 when a rebuilt Common gave 'corrupted' despite matching
archives). So install copies each archive to BOTH places with the same
timestamp, re-stamps the icon, and the game boots straight in, no reinstall. If the installed folder does not
exist yet, the game installs it on first boot as usual. --reinstall restores
the old behaviour (wipe the installed copy and let the game reinstall).

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


def copy_both(src, disc_dst, hdd_dst, reinstall=False):
    """Copy to the disc folder and, if the game data is installed, to the
    installed copy too, with one identical modification time (the game's
    check compares size and mtime)."""
    shutil.copy2(src, disc_dst)
    if not reinstall and os.path.isdir(os.path.dirname(hdd_dst)):
        shutil.copy2(src, hdd_dst)
        st = os.stat(disc_dst)
        os.utime(hdd_dst, ns=(st.st_atime_ns, st.st_mtime_ns))


def install(build_dir, rpcs3, reinstall=False):
    disc = disc_usrdir(rpcs3)
    usrdir = os.path.join(build_dir, "USRDIR")
    n = 0
    eboot = os.path.join(usrdir, "EBOOT.BIN")
    if os.path.exists(eboot):
        shutil.copy2(eboot, os.path.join(disc, "EBOOT.BIN"))
        print("  installed EBOOT.BIN")
        n += 1
    archives = 0
    hdd_psarc = os.path.join(rpcs3, "dev_hdd0", "game", SERIAL, "USRDIR", "PSARC")
    psarc_dir = os.path.join(usrdir, "PSARC")
    if os.path.isdir(psarc_dir):
        for f in sorted(os.listdir(psarc_dir)):
            if f.endswith(".psarc.sdat"):
                src, dst = os.path.join(psarc_dir, f), os.path.join(disc, "PSARC", f)
                if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
                    print("  %s unchanged" % f)
                    continue
                copy_both(src, dst, os.path.join(hdd_psarc, f), reinstall)
                print("  installed %s" % f)
                n += 1
                archives += 1
    if archives and reinstall:
        wipe_installed(rpcs3)
    elif archives:
        stamp_icon(rpcs3)
    print("deployed %d file(s)" % n)


def stamp_icon(rpcs3):
    """The game writes its own ICON0.PNG into the installed folder and gives
    it the modification time of PSARC/Common.psarc.sdat (the first PsarcList
    entry, whole seconds). On boot it stats that icon and shows the
    'corrupted' message if the stamp no longer matches the disc archive, so
    re-stamp it after every deploy (found 2026-10-09 after Common changed)."""
    gd = os.path.join(rpcs3, "dev_hdd0", "game", SERIAL)
    icon = os.path.join(gd, "ICON0.PNG")
    common = os.path.join(gd, "USRDIR", "PSARC", "Common.psarc.sdat")
    if os.path.exists(icon) and os.path.exists(common):
        t = int(os.stat(common).st_mtime)
        os.utime(icon, (t, t))
        print("  re-stamped ICON0.PNG with Common's mtime")


def rollback(rpcs3, pristine):
    disc = disc_usrdir(rpcs3)
    n = 0
    for a in ARCHIVES:
        src = os.path.join(pristine, "PSARC", a + ".psarc.sdat")
        dst = os.path.join(disc, "PSARC", a + ".psarc.sdat")
        if not filecmp.cmp(src, dst, shallow=False):
            copy_both(src, dst, os.path.join(rpcs3, "dev_hdd0", "game", SERIAL, "USRDIR", "PSARC",
                                             a + ".psarc.sdat"))
            print("  restored %s" % dst)
            n += 1
    src = os.path.join(pristine, "EBOOT.BIN")
    dst = os.path.join(disc, "EBOOT.BIN")
    if not filecmp.cmp(src, dst, shallow=False):
        shutil.copy2(src, dst)
        print("  restored %s" % dst)
        n += 1
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
        install(argv[2], rpcs3, "--reinstall" in argv)
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
