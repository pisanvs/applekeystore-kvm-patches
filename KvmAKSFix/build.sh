#!/bin/bash
# build.sh — Build KvmAKSFix.kext (Lilu plugin) on a macOS VM/machine.
#
# Prerequisites (run once):
#   mkdir -p ~/lilu-build
#   cd ~/lilu-build
#   git clone --depth 1 https://github.com/acidanthera/Lilu.git
#   cd Lilu && git clone --depth 1 https://github.com/acidanthera/MacKernelSDK.git
#
# Usage:
#   ./build.sh              → produces build/KvmAKSFix.kext
#   LILU_SRC=<path> ./build.sh
set -euo pipefail
cd "$(dirname "$0")"

LILU_SRC="${LILU_SRC:-$HOME/lilu-build/Lilu}"
LILU_HEADERS="$LILU_SRC/Lilu"
MKSDK="$LILU_SRC/MacKernelSDK"
PRODUCT=KvmAKSFix
VERSION=1.0.0

if [[ ! -d "$MKSDK/Headers" ]]; then
    echo "ERROR: MacKernelSDK not found at $MKSDK"
    echo "Run: cd $LILU_SRC && git clone --depth 1 https://github.com/acidanthera/MacKernelSDK.git"
    exit 1
fi

OUT=build
rm -rf "$OUT"
mkdir -p "$OUT/${PRODUCT}.kext/Contents/MacOS"

CXXFLAGS=(
    -arch x86_64
    -mmacosx-version-min=10.14
    -I "$LILU_HEADERS"
    -I "$MKSDK/Headers"
    -DPRODUCT_NAME=${PRODUCT}
    -DMODULE_VERSION=${VERSION}
    -D__KERNEL__ -DKERNEL -DKERNEL_PRIVATE -DDRIVER_PRIVATE -DAPPLE -DNeXT
    -std=c++17
    -fno-builtin -fno-rtti -fno-exceptions -fno-common
    -fapple-kext -mkernel
    -O2
    -Wall -Wno-unused-parameter -Wno-unknown-warning-option
)

echo "Compiling ${PRODUCT}.cpp ..."
clang++ "${CXXFLAGS[@]}" -c Sources/${PRODUCT}.cpp -o "$OUT/${PRODUCT}.o"

echo "Compiling plugin_start.cpp ..."
clang++ "${CXXFLAGS[@]}" -c "$LILU_HEADERS/Library/plugin_start.cpp" -o "$OUT/plugin_start.o"

echo "Linking ..."
ld \
    -arch x86_64 \
    -static -kext -Z -no_uuid \
    -current_version ${VERSION} -compatibility_version 1.0.0 \
    -undefined dynamic_lookup \
    -L "$MKSDK/Library/x86_64" \
    "$OUT/${PRODUCT}.o" "$OUT/plugin_start.o" \
    -lkmod \
    -o "$OUT/${PRODUCT}.kext/Contents/MacOS/${PRODUCT}"

cp Resources/Info.plist "$OUT/${PRODUCT}.kext/Contents/Info.plist"

echo
echo "=== Built: $OUT/${PRODUCT}.kext ==="
file "$OUT/${PRODUCT}.kext/Contents/MacOS/${PRODUCT}"
echo
echo "Install to OC:"
echo "  sudo cp -r $OUT/${PRODUCT}.kext /path/to/EFI/OC/Kexts/"
echo "Then add to config.plist Kernel → Add:"
echo "  BundlePath: ${PRODUCT}.kext"
echo "  ExecutablePath: Contents/MacOS/${PRODUCT}"
echo "  PlistPath: Contents/Info.plist"
echo "  Enabled: true, MinKernel: 20.0.0"
