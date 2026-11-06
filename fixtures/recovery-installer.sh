#!/sbin/sh
OUTFD="$2"
ZIPFILE="$3"
ui_print() { echo "ui_print $*" > /proc/self/fd/"$OUTFD"; echo ui_print > /proc/self/fd/"$OUTFD"; }
abort() { ui_print "ERROR: $*"; exit 1; }
ui_print "@TITLE@"
DEV="$(getprop ro.product.device)"
[ "$DEV" = lavender ] || abort "Recovery must report lavender; found $DEV."
BLOCK=/dev/block/bootdevice/by-name/boot
[ -b "$BLOCK" ] || abort "lavender boot partition not found."
command -v sha256sum >/dev/null 2>&1 || abort "Recovery needs sha256sum."
SIZE="$(blockdev --getsize64 "$BLOCK" 2>/dev/null)"
[ "$SIZE" = 67108864 ] || abort "Expected a 64 MiB boot partition; found $SIZE."
TMP="$(mktemp /tmp/conq-kernel-XXXXXX)" || abort "Cannot create temporary image."
trap 'rm -f "$TMP"' EXIT
unzip -p "$ZIPFILE" boot.img > "$TMP" || abort "Could not extract boot image."
HASH="$(sha256sum "$TMP")"; HASH="${HASH%% *}"
[ "$HASH" = @SHA256@ ] || abort "Boot image checksum mismatch."
[ "$(wc -c < "$TMP" | tr -d ' ')" = "$SIZE" ] || abort "Boot image size mismatch."
ui_print "Image verified. Writing boot partition only..."
dd if="$TMP" of="$BLOCK" bs=1048576 || abort "Boot write failed. Use the supplied restore ZIP."
sync
HASH="$(sha256sum "$BLOCK")"; HASH="${HASH%% *}"
[ "$HASH" = @SHA256@ ] || abort "Boot readback mismatch. Use the supplied restore ZIP."
ui_print "Boot partition readback verified."
exit 0
