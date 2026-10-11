#!/usr/bin/env bash
# Enable compressed-RAM swap for the build VM. Run as root after every WSL start, before building:
#
#   wsl.exe -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/wsl-zram.sh
#
# Why: Soong's analysis of Android 16 needs ~38 GB. On a 32 GB host the VM gets ~24 GB, and
# swapping the rest to a (USB) disk made soong_build spend >70% of its time in I/O wait.
# zram keeps the overflow in RAM, compressed (Go heaps compress about 3:1), with the disk
# swap from .wslconfig only as a last resort.
set -euo pipefail
SIZE="${ZRAM_SIZE:-44G}"

modprobe zram
if swapon --show=NAME --noheadings | grep -q '^/dev/zram0$'; then
  echo "zram0 already active"
else
  echo 1 > /sys/block/zram0/reset 2>/dev/null || true
  echo "$SIZE" > /sys/block/zram0/disksize
  mkswap /dev/zram0 >/dev/null
  swapon -p 100 /dev/zram0
fi
sysctl -q -w vm.swappiness=100 vm.page-cluster=0
swapon --show
