#!/usr/bin/env python3
"""
find_patches.py — Locate AppleKeyStore REQUIRE patch bytes in a macOS
                   BootKernelExtensions.kc for use with OpenCore Kernel Patch.

Usage:
    python3 find_patches.py <path-to-BootKernelExtensions.kc>

Copy BootKernelExtensions.kc from a running macOS VM:
    scp -P 2222 user@localhost:/System/Library/KernelCollections/BootKernelExtensions.kc .
"""

import sys
import struct
import base64

def get_aks_region(data: bytes) -> tuple[int, int]:
    """Find AppleKeyStore FILESET_ENTRY: returns (fileoff, vmaddr)."""
    AKS_ID = b"com.apple.driver.AppleKeyStore"
    idx = data.find(AKS_ID)
    if idx == -1:
        raise RuntimeError("AppleKeyStore not found in KC")
    # Walk backwards from the bundle ID string to find the LC_FILESET_ENTRY
    # The vmaddr and fileoff are in the load command header
    for off in range(idx, max(0, idx - 4096), -1):
        # LC_FILESET_ENTRY = 0x80000028
        if data[off:off+4] == b"\x28\x00\x00\x80":
            vmaddr  = struct.unpack_from("<Q", data, off + 8)[0]
            fileoff = struct.unpack_from("<Q", data, off + 16)[0]
            return fileoff, vmaddr
    raise RuntimeError("Could not find LC_FILESET_ENTRY for AppleKeyStore")


def find_require_handler(data: bytes, aks_fileoff: int, aks_size: int = 0x95000) -> int:
    """Find the REQUIRE handler target by locating the known _compact_bag_unlock prologue."""
    # Standard function prologue: push rbp; mov rbp, rsp; push r15 ... push rbx; sub rsp, N
    # Then a call to a condition function, then REQUIRE setup+call
    # We search for 'movzx edi, al' (0f b6 f8) followed by 'lea rdx' (48 8d 15) which
    # precedes the REQUIRE call in both target functions.
    region = data[aks_fileoff: aks_fileoff + aks_size]
    pattern = bytes.fromhex("0fb6f8488d15")
    hits = []
    start = 0
    while True:
        idx = region.find(pattern, start)
        if idx == -1:
            break
        # The REQUIRE call should be within 16 bytes after this pattern
        for delta in range(7, 20):
            if region[idx + delta] == 0xe8:
                call_off = aks_fileoff + idx + delta
                disp = struct.unpack_from("<i", data, call_off + 1)[0]
                target = call_off + 5 + disp
                hits.append((call_off, target))
                break
        start = idx + 1

    if not hits:
        raise RuntimeError("Could not find REQUIRE call sites")

    # The REQUIRE handler is the most-common target
    from collections import Counter
    target_counts = Counter(t for _, t in hits)
    require_target = target_counts.most_common(1)[0][0]
    return require_target


def find_all_require_calls(data: bytes, aks_fileoff: int, require_target: int,
                            aks_size: int = 0x95000) -> list[int]:
    """Find all calls to the REQUIRE handler within the AKS region."""
    region = data[aks_fileoff: aks_fileoff + aks_size]
    calls = []
    for i in range(len(region) - 5):
        if region[i] != 0xe8:
            continue
        disp = struct.unpack_from("<i", region, i + 1)[0]
        target = aks_fileoff + i + 5 + disp
        if target == require_target:
            calls.append(aks_fileoff + i)
    return calls


def extract_patch(data: bytes, call_off: int, context: int = 5) -> tuple[bytes, bytes]:
    """
    Build (find, replace) patch bytes.
    find    = <context bytes before call> + <5-byte call>
    replace = <context bytes before call> + <5 NOPs>
    """
    find_bytes    = data[call_off - context: call_off + 5]
    replace_bytes = data[call_off - context: call_off] + b"\x90" * 5
    return find_bytes, replace_bytes


def find_function_start(data: bytes, call_off: int, max_lookback: int = 512) -> int | None:
    prologue = bytes([0x55, 0x48, 0x89, 0xE5])
    for i in range(call_off, max(0, call_off - max_lookback), -1):
        if data[i:i+4] == prologue:
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

    print("Locating AppleKeyStore FILESET_ENTRY ...")
    aks_fileoff, aks_vmaddr = get_aks_region(data)
    print(f"  fileoff={aks_fileoff}  vmaddr={aks_vmaddr:#x}")

    print("Finding REQUIRE handler ...")
    req_target = find_require_handler(data, aks_fileoff)
    print(f"  REQUIRE handler at file offset {req_target}")

    print("Scanning for all REQUIRE call sites in AppleKeyStore ...")
    calls = find_all_require_calls(data, aks_fileoff, req_target)
    print(f"  Found {len(calls)} REQUIRE assertions")

    # The two functions we care about are near each other.
    # _compact_bag_unlock and _compact_bag_lock have a characteristic setup:
    #   movzx edi, al  →  lea rdx, [rip+x] (→ "utils.c")  →  mov esi, N  →  call REQUIRE
    # We identify them by having this exact sequence immediately before the call.
    targets = {}
    for call_off in calls:
        ctx = data[call_off - 16: call_off]
        # Must have: 0f b6 f8 (movzx edi, al) somewhere in the context
        if b"\x0f\xb6\xf8" not in ctx:
            continue
        # Must have: 48 8d 15 (lea rdx, [rip+x]) in context
        if b"\x48\x8d\x15" not in ctx:
            continue
        func_start = find_function_start(data, call_off)
        if func_start is None:
            continue
        offset_in_func = call_off - func_start
        find_b, repl_b = extract_patch(data, call_off)
        if data.count(find_b) == 1:  # unique pattern only
            targets[call_off] = {
                "func_start": func_start,
                "offset_in_func": offset_in_func,
                "find": find_b,
                "replace": repl_b,
            }

    if not targets:
        print("ERROR: Could not identify target REQUIRE call sites with unique patterns.")
        sys.exit(1)

    print(f"\nFound {len(targets)} unique patchable REQUIRE assertions:\n")
    for i, (call_off, info) in enumerate(sorted(targets.items()), 1):
        find_b = info["find"]
        repl_b = info["replace"]
        print(f"  Patch {i}:")
        print(f"    Function start : {info['func_start']} (+{info['offset_in_func']:#x} to REQUIRE call)")
        print(f"    Find  (hex)    : {find_b.hex()}")
        print(f"    Replace (hex)  : {repl_b.hex()}")
        print(f"    Find  (base64) : {base64.b64encode(find_b).decode()}")
        print(f"    Replace(base64): {base64.b64encode(repl_b).decode()}")
        print()


if __name__ == "__main__":
    main()
