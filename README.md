DISCLAIMER: This code was completely designed by Claude. There's probably some edge cases missing, but this fixed my install completely. Please send issues!

# AppleKeyStore KVM Patches

OpenCore kernel patches that fix macOS **Sonoma (14.x)** kernel panics on KVM/QEMU when running without Secure Enclave Processor (SEP) hardware.

## The Problem

macOS Sonoma panics at login and again ~45 minutes later with:

```
panic: "REQUIRE" @ utils.c:1036
Kexts in backtrace: com.apple.driver.AppleKeyStore
```

**Root cause:** Sonoma's `AppleKeyStore.kext` unconditionally routes authentication through the Secure Enclave Processor (SEP) — even with FileVault *off*. KVM has no SEP, so the `REQUIRE(sep_available())` assertion fires and the kernel panics.

Two code paths trigger this:

| Function | Trigger | Crash timing |
|---|---|---|
| `_compact_bag_unlock` | Password authentication | Immediately at login |
| `_compact_bag_lock` | Periodic lock timer | Every ~45 minutes |

## The Fix

Two OpenCore `Kernel → Patch` entries that NOP the REQUIRE call in each function, letting execution continue past the SEP guard.

### Compatibility

| macOS | Kernel | Status |
|---|---|---|
| Sonoma 14.x | 23.x | ✅ Tested on 14.8.7 (xnu-10063.141.1.712.16~1) |
| Sequoia 15.x | 24.x | ❌ Different offsets — patches will not apply (see [Finding new offsets](#finding-new-offsets)) |

## Applying the Patches

Add both entries to the `Kernel → Patch` array in your `config.plist`:

```xml
<!-- Patch 1: _compact_bag_unlock (login crash) -->
<dict>
    <key>Arch</key>
    <string>x86_64</string>
    <key>Base</key>
    <string></string>
    <key>Comment</key>
    <string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_unlock [KVM fix]</string>
    <key>Count</key>
    <integer>1</integer>
    <key>Enabled</key>
    <true/>
    <key>Find</key>
    <data>vpUKAADoQ2r//w==</data>
    <key>Identifier</key>
    <string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key>
    <integer>0</integer>
    <key>Mask</key>
    <data></data>
    <key>MaxKernel</key>
    <string>23.9.9</string>
    <key>MinKernel</key>
    <string>23.0.0</string>
    <key>Replace</key>
    <data>vpUKAACQkJCQkA==</data>
    <key>ReplaceMask</key>
    <data></data>
    <key>Skip</key>
    <integer>0</integer>
</dict>

<!-- Patch 2: _compact_bag_lock (timer crash, ~45min after boot) -->
<dict>
    <key>Arch</key>
    <string>x86_64</string>
    <key>Base</key>
    <string></string>
    <key>Comment</key>
    <string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_lock [KVM timer fix]</string>
    <key>Count</key>
    <integer>1</integer>
    <key>Enabled</key>
    <true/>
    <key>Find</key>
    <data>vl0KAADoCm3//w==</data>
    <key>Identifier</key>
    <string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key>
    <integer>0</integer>
    <key>Mask</key>
    <data></data>
    <key>MaxKernel</key>
    <string>23.9.9</string>
    <key>MinKernel</key>
    <string>23.0.0</string>
    <key>Replace</key>
    <data>vl0KAACQkJCQkA==</data>
    <key>ReplaceMask</key>
    <data></data>
    <key>Skip</key>
    <integer>0</integer>
</dict>
```

**Hex reference:**

| Patch | Find (hex) | Replace (hex) |
|---|---|---|
| `_compact_bag_unlock` | `be950a0000e8436affff` | `be950a00009090909090` |
| `_compact_bag_lock` | `be5d0a0000e80a6dffff` | `be5d0a000090909090 90` |

Or use the helper script to add them automatically:

```bash
# Mount your OpenCore EFI partition first (e.g. at /mnt/opencore)
sudo python3 scripts/apply_patches.py --plist /mnt/opencore/EFI/OC/config.plist
```

## How It Works

OpenCore applies these patches to `AppleKeyStore.kext` in memory at boot before the kernel loads it. Each patch replaces a 5-byte `call` instruction (the REQUIRE panic handler) with 5 `NOP` instructions, skipping the assertion without affecting the rest of the function.

```
Before:  be 95 0a 00 00   mov esi, <arg>
         e8 43 6a ff ff   call _REQUIRE_func   ← panics if no SEP
After:   be 95 0a 00 00   mov esi, <arg>
         90 90 90 90 90   nop nop nop nop nop  ← skipped
```

## Finding New Offsets

If you're on a different macOS version, the byte patterns will differ. The `scripts/find_patches.py` script automates the analysis:

```bash
# Copy BootKernelExtensions.kc from the macOS VM first:
# scp -P 2222 user@localhost:/System/Library/KernelCollections/BootKernelExtensions.kc .

python3 scripts/find_patches.py BootKernelExtensions.kc
```

This finds the REQUIRE call sites in `_compact_bag_unlock` and `_compact_bag_lock` and prints the patch bytes ready to paste into config.plist.

## Environment

Tested on:
- Host: Arch Linux, QEMU 11.0.0, libvirt, KVM (Intel i5-11400 / Rocket Lake)
- Guest: macOS Sonoma 14.8.7
- Bootloader: OpenCore 1.0.6 (from [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM))
- No SEP, no FileVault

## References

- [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM) — the KVM macOS project this was developed against
- OpenCore [Kernel Patch documentation](https://dortania.github.io/OpenCore-Install-Guide/config.plist/haswell.html#kernel)
