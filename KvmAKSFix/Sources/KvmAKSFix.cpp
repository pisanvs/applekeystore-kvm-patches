//
// KvmAKSFix.cpp — Lilu plugin that neuters AppleKeyStore's SEP REQUIRE checks
// so macOS doesn't panic when running under KVM (no Secure Enclave Processor).
//
// Strategy: when AppleKeyStore loads, resolve `_REQUIRE_func` via Lilu's
// symbol resolver and overwrite its prologue with `xor eax, eax; ret`.
// This silences every REQUIRE site in the kext with one patch, regardless
// of which code path triggers it or which macOS version moves the bytes.
//
// Verified on: macOS Sequoia 15.7.7 / Darwin 24.6.0 (xnu-11417.140.69.710.16~1)
// 2h+ uptime achieved; previously panicked within ~21 seconds.
//

#include <Headers/plugin_start.hpp>
#include <Headers/kern_api.hpp>
#include <Headers/kern_patcher.hpp>
#include <Headers/kern_mach.hpp>
#include <Headers/kern_util.hpp>

static const char *kAppleKeyStorePath[] {
    "/System/Library/Extensions/AppleKeyStore.kext/Contents/MacOS/AppleKeyStore"
};

static KernelPatcher::KextInfo kAppleKeyStoreInfo {
    "com.apple.driver.AppleKeyStore",
    kAppleKeyStorePath,
    arrsize(kAppleKeyStorePath),
    {true, true},
    {},
    KernelPatcher::KextInfo::Unloaded
};

static bool patched = false;

static void onKextLoad(void *, KernelPatcher &patcher, size_t index, mach_vm_address_t address, size_t size) {
    if (patched || index != kAppleKeyStoreInfo.loadIndex)
        return;

    auto reqAddr = patcher.solveSymbol(index, "_REQUIRE_func", address, size);
    if (!reqAddr) {
        SYSLOG("kvmaks", "could not resolve _REQUIRE_func (patcher err %d) — no patch applied", patcher.getError());
        patcher.clearError();
        return;
    }

    SYSLOG("kvmaks", "resolved _REQUIRE_func @ 0x%llx", reqAddr);

    // xor eax, eax  (31 C0)  — return 0
    // ret           (C3)
    // nop; nop      (90 90)  — padding to preserve size
    const uint8_t stub[5] = { 0x31, 0xC0, 0xC3, 0x90, 0x90 };

    if (MachInfo::setKernelWriting(true, KernelPatcher::kernelWriteLock) != KERN_SUCCESS) {
        SYSLOG("kvmaks", "failed to enable kernel writing");
        return;
    }
    memcpy(reinterpret_cast<void *>(reqAddr), stub, sizeof(stub));
    MachInfo::setKernelWriting(false, KernelPatcher::kernelWriteLock);

    patched = true;
    SYSLOG("kvmaks", "patched _REQUIRE_func @ 0x%llx → xor eax,eax; ret", reqAddr);
    // Verify by checking after boot:
    //   sudo dmesg | grep kvmaks
}

static void pluginStart() {
    SYSLOG("kvmaks", "start (build " __DATE__ " " __TIME__ ")");
    lilu.onKextLoadForce(&kAppleKeyStoreInfo, 1, onKextLoad, nullptr);
}

static const char *bootargOff[]   { "-kvmaksoff" };
static const char *bootargDebug[] { "-kvmaksdbg" };
static const char *bootargBeta[]  { "-kvmaksbeta" };

PluginConfiguration ADDPR(config) {
    xStringify(PRODUCT_NAME),
    parseModuleVersion(xStringify(MODULE_VERSION)),
    LiluAPI::AllowNormal | LiluAPI::AllowInstallerRecovery | LiluAPI::AllowSafeMode,
    bootargOff,   arrsize(bootargOff),
    bootargDebug, arrsize(bootargDebug),
    bootargBeta,  arrsize(bootargBeta),
    KernelVersion::Sonoma,
    KernelVersion::Sequoia,
    pluginStart
};
