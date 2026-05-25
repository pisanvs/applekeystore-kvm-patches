#!/usr/bin/env python3
"""
apply_patches.py — Add AppleKeyStore KVM patches to an OpenCore config.plist.

Usage:
    sudo python3 apply_patches.py --plist /mnt/opencore/EFI/OC/config.plist

Creates a .bak backup before modifying.
"""

import argparse
import plistlib
import shutil
from pathlib import Path

PATCHES = [
    {
        "Arch":        "x86_64",
        "Base":        "",
        "Comment":     "AppleKeyStore: NOP SEP REQUIRE in _compact_bag_unlock [KVM fix]",
        "Count":       1,
        "Enabled":     True,
        "Find":        bytes.fromhex("be950a0000e8436affff"),
        "Identifier":  "com.apple.driver.AppleKeyStore",
        "Limit":       0,
        "Mask":        b"",
        "MaxKernel":   "23.9.9",
        "MinKernel":   "23.0.0",
        "Replace":     bytes.fromhex("be950a00009090909090"),
        "ReplaceMask": b"",
        "Skip":        0,
    },
    {
        "Arch":        "x86_64",
        "Base":        "",
        "Comment":     "AppleKeyStore: NOP SEP REQUIRE in _compact_bag_lock [KVM timer fix]",
        "Count":       1,
        "Enabled":     True,
        "Find":        bytes.fromhex("be5d0a0000e80a6dffff"),
        "Identifier":  "com.apple.driver.AppleKeyStore",
        "Limit":       0,
        "Mask":        b"",
        "MaxKernel":   "23.9.9",
        "MinKernel":   "23.0.0",
        "Replace":     bytes.fromhex("be5d0a000090909090 90".replace(" ", "")),
        "ReplaceMask": b"",
        "Skip":        0,
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plist", required=True, help="Path to OpenCore config.plist")
    args = parser.parse_args()

    plist_path = Path(args.plist)
    if not plist_path.exists():
        print(f"ERROR: {plist_path} not found")
        raise SystemExit(1)

    backup = Path(str(plist_path) + ".bak")
    shutil.copy(plist_path, backup)
    print(f"Backup: {backup}")

    with open(plist_path, "rb") as f:
        cfg = plistlib.load(f)

    existing = cfg.setdefault("Kernel", {}).setdefault("Patch", [])
    comments = {p["Comment"] for p in PATCHES}
    existing[:] = [p for p in existing if p.get("Comment") not in comments]
    existing.extend(PATCHES)

    with open(plist_path, "wb") as f:
        plistlib.dump(cfg, f, fmt=plistlib.FMT_XML, sort_keys=False)

    print(f"Applied {len(PATCHES)} patches to {plist_path}")
    for p in PATCHES:
        print(f"  [{'ON' if p['Enabled'] else 'off'}] {p['Comment']}")


if __name__ == "__main__":
    main()
