DISCLAIMER: This code was completely designed by Claude. There's probably some edge cases missing, but this fixed my install completely. Please send issues!

# AppleKeyStore KVM Patches

Fixes macOS **Sonoma (14.x)** and **Sequoia (15.x)** kernel panics on KVM/QEMU when running without a Secure Enclave Processor (SEP).

**Two approaches** — [Lilu plugin](#option-a--lilu-plugin-recommended) (recommended) or [OpenCore patches](#option-b--opencore-kernel-patches-legacy).

---

## The Problem

macOS panics within seconds of login:

```
panic: "REQUIRE" @ utils.c:1061
Kexts in backtrace: com.apple.driver.AppleKeyStore
```

**Root cause:** `AppleKeyStore.kext` unconditionally calls `_REQUIRE_func` — a SEP availability assertion — in `_compact_bag_unlock` (on login) and `_compact_bag_lock` (on a ~82-second timer). KVM has no SEP, so both assertions fire and the kernel panics.

| Function | Trigger | Timing |
|---|---|---|
| `_compact_bag_unlock` | Password authentication | Immediately at login |
| `_compact_bag_lock` | Periodic lock timer | ~82 seconds after boot |

---

## Compatibility

| macOS | Darwin | Build | Status |
|---|---|---|---|
| Sonoma 14.8.7 | 23.x | xnu-10063.141.1.712.16~1 | ✅ Tested |
| Sequoia 15.7.7 | 24.x | xnu-11417.140.69.710.16~1 (24G720) | ✅ Tested — 2h+ uptime |

---

## Option A — Lilu Plugin (Recommended)

A [Lilu](https://github.com/acidanthera/Lilu) kernel extension that resolves `_REQUIRE_func` by symbol at boot and overwrites it with `xor eax, eax; ret`. This:

- **Covers all call sites at once** — any current or future code path in the kext that hits `_REQUIRE_func` is neutralised
- **Survives kernel updates** — uses Lilu's live symbol resolver, not hardcoded byte offsets
- **Verifiable from inside the OS** — check with `sudo dmesg | grep kvmaks` after boot
- **Proven stable** — 2h+ uptime on Sequoia 15.7.7 with Chrome Remote Desktop and general use

### Prerequisites

- [Lilu.kext](https://github.com/acidanthera/Lilu/releases) ≥ 1.6.0 already in your OC Kexts (almost certainly yes if you have a working Hackintosh)
- Xcode or Xcode CLT on a macOS machine to build (can be the VM itself)

### Build

```bash
# 1. Get Lilu source + MacKernelSDK (one-time setup on your macOS machine/VM)
mkdir -p ~/lilu-build && cd ~/lilu-build
git clone --depth 1 https://github.com/acidanthera/Lilu.git
cd Lilu && git clone --depth 1 https://github.com/acidanthera/MacKernelSDK.git

# 2. Build the plugin
cd /path/to/this/repo/KvmAKSFix
chmod +x build.sh && ./build.sh
# → produces build/KvmAKSFix.kext
```

### Install

```bash
# Copy kext to OC (mount your OC EFI partition first)
sudo cp -r build/KvmAKSFix.kext /path/to/EFI/OC/Kexts/
```

Add to `config.plist` → `Kernel → Add`:

```xml
<dict>
    <key>Arch</key><string>Any</string>
    <key>BundlePath</key><string>KvmAKSFix.kext</string>
    <key>Comment</key><string>AppleKeyStore SEP REQUIRE neuterer for KVM</string>
    <key>Enabled</key><true/>
    <key>ExecutablePath</key><string>Contents/MacOS/KvmAKSFix</string>
    <key>MaxKernel</key><string></string>
    <key>MinKernel</key><string>20.0.0</string>
    <key>PlistPath</key><string>Contents/Info.plist</string>
</dict>
```

> **Important:** KvmAKSFix must load **after** Lilu. In OC's Kext list, ensure Lilu appears before KvmAKSFix.

### Verify

After booting:

```bash
sudo dmesg | grep kvmaks
# Expected output:
# kvmaks: start (build May 27 2026 ...)
# kvmaks: resolved _REQUIRE_func @ 0xffffff80...
# kvmaks: patched _REQUIRE_func @ 0xffffff80... → xor eax,eax; ret
```

If you see all three lines, the patch is live and every REQUIRE site in AppleKeyStore is neutralised.

---

## Option B — OpenCore Kernel Patches (Legacy)

> Use this if you can't build the Lilu plugin. These patches use hardcoded byte patterns that may need updating after macOS kernel rebuilds.

### Automatic

```bash
sudo python3 scripts/apply_patches.py --plist /path/to/EFI/OC/config.plist
```

### Manual (XML)

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
<!-- _compact_bag_lock -->
<dict>
    <key>Arch</key><string>x86_64</string>
    <key>Base</key><string></string>
    <key>Comment</key><string>AppleKeyStore: NOP SEP REQUIRE in _compact_bag_lock [KVM fix - Sequoia]</string>
    <key>Count</key><integer>1</integer>
    <key>Enabled</key><true/>
    <key>Find</key><data>vk8LAADoJI37/w==</data>
    <key>Identifier</key><string>kernel</string>
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
    <key>Identifier</key><string>kernel</string>
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

### Updating after a macOS kernel rebuild

If the OC patches stop working after a macOS update, use `find_patches.py` to re-derive the correct bytes:

```bash
# Copy KC from recovery or a running VM:
# scp user@<vm>:'/System/Volumes/Preboot/<UUID>/boot/System/Library/KernelCollections/BootKernelExtensions.kc' .

python3 scripts/find_patches.py BootKernelExtensions.kc
```

Requires `llvm-nm`: `pacman -S llvm` / `brew install llvm`

---

## How It Works

```
Before:  be ef 0a 00 00   mov esi, <line_number>   ; _compact_bag_unlock + 0x3a
         e8 da 83 fb ff   call _REQUIRE_func        ← panics if no SEP

After (Lilu):  _REQUIRE_func prologue becomes:
         31 c0            xor eax, eax              ← return 0 immediately
         c3               ret
         90 90            nop nop

After (OC):    call site becomes:
         90 90 90 90 90   nop nop nop nop nop       ← call skipped
```

The Lilu approach patches the function itself once; the OC approach patches each call site individually and needs updating when kernel bytes change.

---

## AI Assistant Shortcut

Copy this prompt into [Claude Code](https://claude.ai/code) or a similar AI assistant:

```
Read https://github.com/pisanvs/applekeystore-kvm-patches/blob/main/README.md and apply the appropriate patches to fix AppleKeyStore KVM panics on my macOS install. Prefer the Lilu plugin approach if I have Xcode or CLT available.
```

---

## Environment

Tested on:
- **Host:** Arch Linux, QEMU 11.0.0, libvirt/virsh, KVM (Intel i5-11400 / Rocket Lake)
- **Guest:** macOS Sonoma 14.8.7, macOS Sequoia 15.7.7
- **Bootloader:** OpenCore 1.0.6 (from [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM))
- No SEP, no FileVault

## References

- [kholia/OSX-KVM](https://github.com/kholia/OSX-KVM) — the KVM macOS project this was developed against
- [acidanthera/Lilu](https://github.com/acidanthera/Lilu) — kernel patcher kext used by this plugin
- [acidanthera/MacKernelSDK](https://github.com/acidanthera/MacKernelSDK) — kernel SDK for building Lilu plugins
- OpenCore [Kernel Patch documentation](https://dortania.github.io/OpenCore-Install-Guide/config.plist/haswell.html#kernel)
