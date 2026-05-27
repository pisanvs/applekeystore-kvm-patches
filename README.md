DISCLAIMER: This code was completely designed by Claude. There's probably some edge cases missing, but this fixed my install completely. Please send issues!

# AppleKeyStore KVM Patches

OpenCore kernel patches that fix macOS **Sonoma (14.x)** and **Sequoia (15.x)** kernel panics on KVM/QEMU when running without Secure Enclave Processor (SEP) hardware.

## The Problem

macOS panics at login and again ~82 seconds later with:

```
panic: "REQUIRE" @ utils.c:1036
Kexts in backtrace: com.apple.driver.AppleKeyStore
```

**Root cause:** `AppleKeyStore.kext` unconditionally routes authentication through the Secure Enclave Processor (SEP) — even with FileVault *off*. KVM has no SEP, so the `REQUIRE(sep_available())` assertion fires and the kernel panics.

Two code paths trigger this:

| Function | Trigger | Crash timing |
|---|---|---|
| `_compact_bag_unlock` | Password authentication | Immediately at login |
| `_compact_bag_lock` | Periodic lock timer | ~82 seconds after boot |

## The Fix

Two OpenCore `Kernel → Patch` entries that NOP the REQUIRE call in each function, letting execution continue past the SEP guard.

### Compatibility

| macOS | Darwin | Build tested | Status |
|---|---|---|---|
| Sonoma 14.8.7 | 23.x | xnu-10063.141.1.712.16~1 | ✅ Tested |
| Sequoia 15.7.7 | 24.x | xnu-11215.x (24G720) | ✅ Tested |

## Applying the Patches

> **Shortcut:** Copy this prompt and paste it into [Claude Code](https://claude.ai/code) or a similar AI coding assistant — it will read this README and apply the patches to your install automatically:
>
> ```
> Read https://github.com/pisanvs/applekeystore-kvm-patches/blob/main/README.md and apply the appropriate patches to my OpenCore config.plist to fix AppleKeyStore KVM panics on my macOS install.
> ```

### Option A — Automatic (recommended)

```bash
# Mount your OpenCore EFI partition first (e.g. at /mnt/opencore)
sudo python3 scripts/apply_patches.py --plist /mnt/opencore/EFI/OC/config.plist
```

This adds all patches for all supported macOS versions. Each patch is gated by `MinKernel`/`MaxKernel` so only the right one applies at boot.

### Option B — Manual (XML)

Add these entries to the `Kernel → Patch` array in your `config.plist`:

#### Sonoma 14.x

```xml
<!-- _compact_bag_unlock (login crash) -->
<dict>
    <key>Arch</key><string>x86_64</string>
    <key>Base</key><string></string>
    <key>Comment</key><string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_unlock [KVM fix - Sonoma]</string>
    <key>Count</key><integer>1</integer>
    <key>Enabled</key><true/>
    <key>Find</key><data>vpUKAADoQ2r//w==</data>
    <key>Identifier</key><string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key><integer>0</integer>
    <key>Mask</key><data></data>
    <key>MaxKernel</key><string>23.9.9</string>
    <key>MinKernel</key><string>23.0.0</string>
    <key>Replace</key><data>vpUKAACQkJCQkA==</data>
    <key>ReplaceMask</key><data></data>
    <key>Skip</key><integer>0</integer>
</dict>

<!-- _compact_bag_lock (timer crash, ~82s after boot) -->
<dict>
    <key>Arch</key><string>x86_64</string>
    <key>Base</key><string></string>
    <key>Comment</key><string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_lock [KVM fix - Sonoma]</string>
    <key>Count</key><integer>1</integer>
    <key>Enabled</key><true/>
    <key>Find</key><data>vl0KAADoCm3//w==</data>
    <key>Identifier</key><string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key><integer>0</integer>
    <key>Mask</key><data></data>
    <key>MaxKernel</key><string>23.9.9</string>
    <key>MinKernel</key><string>23.0.0</string>
    <key>Replace</key><data>vl0KAACQkJCQkA==</data>
    <key>ReplaceMask</key><data></data>
    <key>Skip</key><integer>0</integer>
</dict>
```

#### Sequoia 15.x

```xml
<!-- _compact_bag_lock (start crash + timer crash) -->
<dict>
    <key>Arch</key><string>x86_64</string>
    <key>Base</key><string></string>
    <key>Comment</key><string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_lock [KVM fix - Sequoia]</string>
    <key>Count</key><integer>1</integer>
    <key>Enabled</key><true/>
    <key>Find</key><data>vk8LAADoJI37/w==</data>
    <key>Identifier</key><string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key><integer>0</integer>
    <key>Mask</key><data></data>
    <key>MaxKernel</key><string>24.9.9</string>
    <key>MinKernel</key><string>24.0.0</string>
    <key>Replace</key><data>vk8LAACQkJCQkA==</data>
    <key>ReplaceMask</key><data></data>
    <key>Skip</key><integer>0</integer>
</dict>

<!-- _compact_bag_unlock (login crash) -->
<dict>
    <key>Arch</key><string>x86_64</string>
    <key>Base</key><string></string>
    <key>Comment</key><string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_unlock [KVM fix - Sequoia]</string>
    <key>Count</key><integer>1</integer>
    <key>Enabled</key><true/>
    <key>Find</key><data>vu8KAADo2oP7/w==</data>
    <key>Identifier</key><string>com.apple.driver.AppleKeyStore</string>
    <key>Limit</key><integer>0</integer>
    <key>Mask</key><data></data>
    <key>MaxKernel</key><string>24.9.9</string>
    <key>MinKernel</key><string>24.0.0</string>
    <key>Replace</key><data>vu8KAACQkJCQkA==</data>
    <key>ReplaceMask</key><data></data>
    <key>Skip</key><integer>0</integer>
</dict>
```

**Hex reference:**

| macOS | Patch | Find (hex) | Replace (hex) |
|---|---|---|---|
| Sonoma | `_compact_bag_unlock` | `be950a0000e8436affff` | `be950a00009090909090` |
| Sonoma | `_compact_bag_lock` | `be5d0a0000e80a6dffff` | `be5d0a00009090909090` |
| Sequoia | `_compact_bag_lock` | `be4f0b0000e8248dfbff` | `be4f0b00009090909090` |
| Sequoia | `_compact_bag_unlock` | `beef0a0000e8da83fbff` | `beef0a00009090909090` |

## How It Works

OpenCore applies these patches to `AppleKeyStore.kext` in memory at boot before the kernel loads it. Each patch replaces a 5-byte `call` instruction (the REQUIRE panic handler) with 5 `NOP` instructions, skipping the assertion without affecting the rest of the function.

```
Before:  be 4f 0b 00 00   mov esi, <line_number>
         e8 24 8d fb ff   call _REQUIRE_func   ← panics if no SEP
After:   be 4f 0b 00 00   mov esi, <line_number>
         90 90 90 90 90   nop nop nop nop nop  ← skipped
```

## Finding New Offsets

If your kernel version isn't listed above, use `find_patches.py` to generate the correct bytes automatically:

```bash
# Copy BootKernelExtensions.kc from recovery or a running VM:
# scp user@<vm>:/System/Volumes/Preboot/<UUID>/boot/System/Library/KernelCollections/BootKernelExtensions.kc .

python3 scripts/find_patches.py BootKernelExtensions.kc
```

Requires `llvm-nm`: `pacman -S llvm` / `brew install llvm`

## Environment

Tested on:
- Host: Arch Linux, QEMU 11.0.0, libvirt/virsh, KVM (Intel i5-11400 / Rocket Lake)
- Guest: macOS Sonoma 14.8.7, macOS Sequoia 15.7.7
- Bootloader: OpenCore 1.0.6 (from [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM))
- No SEP, no FileVault

## References

- [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM) — the KVM macOS project this was developed against
- OpenCore [Kernel Patch documentation](https://dortania.github.io/OpenCore-Install-Guide/config.plist/haswell.html#kernel)
