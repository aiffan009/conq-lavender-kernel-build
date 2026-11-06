#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BUILD_ROOT="$PWD"
mkdir -p .ci/kernel .ci/toolchain .ci/out .ci/KernelSU-Next logs artifacts
exec > >(tee logs/build.log) 2>&1
KERNEL_COMMIT=46b4f3ea4a835fa6a1752d0608f36c9377c5094e
TOOLCHAIN_COMMIT=9fb011b183fe7e69b04b873ef6533b4b077e3c5e
KSU_COMMIT=2241696498ce9dd742ce80b52c3ed6cca26e03ea
curl --fail --location --retry 4 "https://github.com/stormbreaker-project/kernel_xiaomi_lavender/archive/${KERNEL_COMMIT}.tar.gz" -o .ci/kernel.tar.gz
tar -xzf .ci/kernel.tar.gz --strip-components=1 -C .ci/kernel
curl --fail --location --retry 4 "https://github.com/kdrag0n/proton-clang/archive/${TOOLCHAIN_COMMIT}.tar.gz" -o .ci/toolchain.tar.gz
tar -xzf .ci/toolchain.tar.gz --strip-components=1 -C .ci/toolchain
curl --fail --location --retry 4 "https://github.com/KernelSU-Next/KernelSU-Next/archive/${KSU_COMMIT}.tar.gz" -o .ci/ksu.tar.gz
tar -xzf .ci/ksu.tar.gz --strip-components=1 -C .ci/KernelSU-Next
curl --fail --location --retry 4 'https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v1.0.9/KernelSU_Next_v1.0.9_12797-release.apk' -o .ci/official-manager.apk
export PATH="$BUILD_ROOT/.ci/toolchain/bin:$PATH"
clang --version | tee logs/compiler.txt
grep -q 'b4fd512c36ca344a3ff69350219e8b0a67e9472a' logs/compiler.txt
python3 scripts/integrate_ksu.py --kernel .ci/kernel --ksu .ci/KernelSU-Next --manager .ci/official-manager.apk --logs logs
MAKE_ARGS=("O=$BUILD_ROOT/.ci/out" ARCH=arm64 CC=clang CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabi- LOCALVERSION=-conq-ksunext)
make -C .ci/kernel "${MAKE_ARGS[@]}" lavender-perf_defconfig
.ci/kernel/scripts/config --file .ci/out/.config -e OVERLAY_FS -e KALLSYMS -e KALLSYMS_ALL -e KSU -e KSU_LSM_SECURITY_HOOKS -d KSU_KPROBES_HOOK -d KSU_DEBUG
make -C .ci/kernel "${MAKE_ARGS[@]}" olddefconfig
cp .ci/out/.config logs/generated.config
for setting in CONFIG_SCHED_WALT=y CONFIG_CPU_FREQ_GOV_SCHEDUTIL=y CONFIG_SND_SOC_SDM660_COMMON=y CONFIG_QCA_CLD_WLAN=y CONFIG_OVERLAY_FS=y CONFIG_KSU=y CONFIG_KSU_LSM_SECURITY_HOOKS=y CONFIG_KALLSYMS=y; do
  grep -qx "$setting" .ci/out/.config || { echo "Missing required setting: $setting"; exit 1; }
done
if grep -qx 'CONFIG_KSU_KPROBES_HOOK=y' .ci/out/.config; then echo 'KSU kprobe hooks must be disabled for this manual-hook build.'; exit 1; fi
python3 .ci/kernel/scripts/diffconfig configs/conq-original.config .ci/out/.config > logs/config-diff.txt
make -C .ci/kernel "${MAKE_ARGS[@]}" -j"$(nproc)" Image.gz-dtb
aarch64-linux-gnu-nm .ci/out/vmlinux > logs/vmlinux-symbols.txt
for symbol in kernelsu_init ksu_handle_execveat ksu_handle_vfs_read ksu_handle_faccessat ksu_handle_stat ksu_handle_input_handle_event ksu_handle_devpts; do
  grep -q " ${symbol}$" logs/vmlinux-symbols.txt || { echo "Missing linked KSU symbol: $symbol"; exit 1; }
done
make -s -C .ci/kernel "${MAKE_ARGS[@]}" kernelrelease > logs/kernelrelease.txt
cp logs/kernelsu-integration.json artifacts/kernelsu-integration.json
python3 scripts/package_boot.py --kernel .ci/out/arch/arm64/boot/Image.gz-dtb --out artifacts --variant kernelsu-next
echo 'KernelSU Next v1.0.9 / 12797 compiled and packaged. Device test is still required.'
