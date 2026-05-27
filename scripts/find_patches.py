#!/usr/bin/env python3
"""
find_patches.py — Locate AppleKeyStore REQUIRE patch bytes in a macOS
                   BootKernelExtensions.kc for use with OpenCore Kernel Patch.

Usage:
    python3 find_patches.py <path-to-BootKernelExtensions.kc>

Copy BootKernelExtensions.kc from a running macOS VM (or recovery):
    scp user@<vm>:/System/Volumes/Preboot/<UUID>/boot/System/Library/KernelCollections/BootKernelExtensions.kc .

Requires: llvm-nm (pacman -S llvm / brew install llvm)
"""

import sys
import struct
import base64
import subprocess


def parse_segments(data: bytes) -> list[tuple[str, int, int, int]]:
    """Return list of (name, vmaddr, vmsize, fileoff) for all LC_SEGMENT_64."""
    LC_SEGMENT_64 = 0x19
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    segs = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == LC_SEGMENT_64:
            name = data[off + 8: off + 24].rstrip(b"\x00").decode()
            vmaddr, vmsize, fileoff, _ = struct.unpack_from("<QQQQ", data, off + 24)
            segs.append((name, vmaddr, vmsize, fileoff))
        off += cmdsize
    return segs


def va_to_fileoff(segs: list, va: int) -> int | None:
    for _, va_start, va_size, fo_start in segs:
        if va_start <= va < va_start + va_size:
            return fo_start + (va - va_start)
    return None


def get_symbols(kc_path: str, names: list[str]) -> dict[str, int]:
    """Use llvm-nm (or nm) to resolve symbol vmaddrs."""
    for tool in ("llvm-nm", "nm"):
        try:
            out = subprocess.check_output([tool, kc_path], stderr=subprocess.DEVNULL).decode()
            result = {}
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[2] in names:
                    result[parts[2]] = int(parts[0], 16)
            if result:
                return result
        except FileNotFoundError:
            continue
    raise RuntimeError("Neither llvm-nm nor nm found — install llvm (pacman -S llvm / brew install llvm)")


def find_require_call(data: bytes, fn_fileoff: int, require_va: int, fn_va: int) -> int | None:
    """Find the call to _REQUIRE_func within a function, return offset from fn start."""
    for i in range(0, 0x100):
        if data[fn_fileoff + i] != 0xe8:
            continue
        disp = struct.unpack_from("<i", data, fn_fileoff + i + 1)[0]
        call_va = fn_va + i + 5 + disp
        if call_va == require_va:
            return i
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    kc_path = sys.argv[1]
    print(f"Reading {kc_path} ...")
    with open(kc_path, "rb") as f:
        data = f.read()

    print("Parsing segments ...")
    segs = parse_segments(data)

    print("Resolving symbols via nm ...")
    sym_names = ["_compact_bag_lock", "_compact_bag_unlock", "_REQUIRE_func"]
    syms = get_symbols(kc_path, sym_names)

    for s in sym_names:
        if s not in syms:
            print(f"ERROR: symbol {s} not found — is this a valid BootKernelExtensions.kc?")
            sys.exit(1)

    require_va = syms["_REQUIRE_func"]
    print(f"  _REQUIRE_func vmaddr: {require_va:#x}")

    patches = []
    for sym in ("_compact_bag_lock", "_compact_bag_unlock"):
        fn_va = syms[sym]
        fn_fo = va_to_fileoff(segs, fn_va)
        if fn_fo is None:
            print(f"ERROR: cannot map {sym} vmaddr {fn_va:#x} to file offset")
            sys.exit(1)

        call_rel = find_require_call(data, fn_fo, require_va, fn_va)
        if call_rel is None:
            print(f"ERROR: no call to _REQUIRE_func found in {sym}")
            sys.exit(1)

        call_fo = fn_fo + call_rel
        find_bytes    = data[call_fo - 5: call_fo + 5]
        replace_bytes = data[call_fo - 5: call_fo] + b"\x90" * 5

        if data.count(find_bytes) != 1:
            print(f"WARNING: Find pattern for {sym} is not unique ({data.count(find_bytes)} hits) — use with care")

        patches.append((sym, fn_va, call_rel, call_fo, find_bytes, replace_bytes))

    print(f"\nFound {len(patches)} patches:\n")
    for sym, fn_va, call_rel, call_fo, find_b, repl_b in patches:
        print(f"  {sym}:")
        print(f"    vmaddr        : {fn_va:#x}  (+{call_rel:#x} to REQUIRE call)")
        print(f"    fileoff       : {call_fo - 5:#x}  (patch at {call_fo:#x})")
        print(f"    Find  (hex)   : {find_b.hex()}")
        print(f"    Replace (hex) : {repl_b.hex()}")
        print(f"    Find  (b64)   : {base64.b64encode(find_b).decode()}")
        print(f"    Replace (b64) : {base64.b64encode(repl_b).decode()}")
        print()


if __name__ == "__main__":
    main()
