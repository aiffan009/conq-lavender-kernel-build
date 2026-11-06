#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BUILD_ROOT="$PWD"
mkdir -p .ci/kernel .ci/toolchain .ci/out logs artifacts
exec > >(tee logs/build.log) 2>&1
KERNEL_COMMIT="$(python3 -c 'import json; print(json.load(open("build-lock.json"))["kernel_commit"])')"
TOOLCHAIN_COMMIT="$(python3 -c 'import json; print(json.load(open("build-lock.json"))["toolchain_commit"])')"
curl --fail --location --retry 4 "https://github.com/stormbreaker-project/kernel_xiaomi_lavender/archive/${KERNEL_COMMIT}.tar.gz" -o .ci/kernel.tar.gz
tar -xzf .ci/kernel.tar.gz --strip-components=1 -C .ci/kernel
curl --fail --location --retry 4 "https://github.com/kdrag0n/proton-clang/archive/${TOOLCHAIN_COMMIT}.tar.gz" -o .ci/toolchain.tar.gz
tar -xzf .ci/toolchain.tar.gz --strip-components=1 -C .ci/toolchain
export PATH="$BUILD_ROOT/.ci/toolchain/bin:$PATH"
clang --version | tee logs/compiler.txt
grep -q 'b4fd512c36ca344a3ff69350219e8b0a67e9472a' logs/compiler.txt
cp configs/conq-original.config .ci/out/.config
MAKE_ARGS=("O=$BUILD_ROOT/.ci/out" ARCH=arm64 CC=clang CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabi- LOCALVERSION=-conq-baseline)
make -C .ci/kernel "${MAKE_ARGS[@]}" olddefconfig
cp .ci/out/.config logs/generated.config
python3 .ci/kernel/scripts/diffconfig configs/conq-original.config .ci/out/.config > logs/config-diff.txt
make -C .ci/kernel "${MAKE_ARGS[@]}" -j"$(nproc)" Image.gz-dtb
test -s .ci/out/arch/arm64/boot/Image.gz-dtb
make -s -C .ci/kernel "${MAKE_ARGS[@]}" kernelrelease > logs/kernelrelease.txt
cp build-lock.json artifacts/build-lock.json
python3 scripts/package_boot.py --kernel .ci/out/arch/arm64/boot/Image.gz-dtb --out artifacts
echo "Baseline compiled. This build intentionally does not contain KernelSU. Test boot compatibility before integrating KernelSU Next."
