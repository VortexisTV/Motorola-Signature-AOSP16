#!/usr/bin/env bash
# Bootstrap the dedicated "moto-aosp" WSL distro (Ubuntu 24.04) used to build
# AOSP 16 / TrebleDroid and to analyse the Motorola stock firmware.
#
#   wsl.exe -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/wsl-bootstrap.sh
#
# Idempotent. /proj must point at this repository (see BUILDING.md).
set -euo pipefail
BUILD_USER="${BUILD_USER:-builder}"
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
# AOSP build prerequisites
apt-get install -y --no-install-recommends \
  git git-lfs gnupg flex bison build-essential zip unzip curl wget zlib1g-dev \
  libc6-dev-i386 x11proto-core-dev libx11-dev lib32z1-dev libgl1-mesa-dev \
  libxml2-utils xsltproc fontconfig rsync bc ccache lz4 zstd openssl libssl-dev \
  python3 python-is-python3 python3-pip python3-venv ca-certificates \
  openjdk-21-jdk-headless
# Firmware analysis tooling (setools: validate-image.sh compares the compiled SELinux policy with stock)
apt-get install -y --no-install-recommends \
  erofs-utils android-sdk-libsparse-utils e2fsprogs p7zip-full cpio binutils file \
  device-tree-compiler xxd jq sqlite3 attr python3-pyelftools python3-lxml \
  python3-protobuf python3-yaml python3-setools setools aapt apktool

id "$BUILD_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$BUILD_USER"
echo "$BUILD_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$BUILD_USER"
chmod 0440 "/etc/sudoers.d/90-$BUILD_USER"

cat > /etc/wsl.conf <<CONF
[boot]
systemd=true

[user]
default=$BUILD_USER

[interop]
appendWindowsPath=false
CONF

curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o /usr/local/bin/repo
chmod 0755 /usr/local/bin/repo

install -d -o "$BUILD_USER" -g "$BUILD_USER" /work /work/aosp /work/fw /work/out /work/ccache /work/tools

sudo -u "$BUILD_USER" -H bash -c '
  git config --global user.name  "vantage-rom-builder"
  git config --global user.email "builder@localhost"
  git config --global color.ui false
  git config --global advice.detachedHead false
  CCACHE_DIR=/work/ccache ccache -M 50G >/dev/null
'
echo "bootstrap complete"
