#!/usr/bin/env bash
# src/bin/freerdp/build.sh
# Rebuild FreeRDP 3.x with USB + audio support for PyRDPConnect (Pi)
# Can be dropped in either the FreeRDP source root *or* the build directory.

set -euo pipefail

########################################################
# Configurable variables
########################################################

# FreeRDP git repository & branch to use
REPO_URL="https://github.com/FreeRDP/FreeRDP.git"
REPO_BRANCH="master"

########################################################
# Project root & detect OS/arch
########################################################

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

UNAME_OS="$(uname -s)"
case "$UNAME_OS" in
    Linux)
        OS="linux"
        ;;
    Darwin)
        OS="macos"
        ;;
    *)
        echo "Unsupported OS: $UNAME_OS" >&2
        exit 1
        ;;
esac

ARCH="$(uname -m)"
case "$ARCH" in
    i386|i686|x86|i86pc)
        ARCH="x86_64"
        ;;
    amd64|x86_64)
        ARCH="x86_64"
        ;;
    armv6l|armv7l|armhf)
        ARCH="armhf"
        ;;
    aarch64|arm64)
        ARCH="arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH" >&2
        exit 1
        ;;
esac

########################################################
# Define source, build, and install directories
########################################################

SOURCE_DIR="${PROJECT_ROOT}/src/bin/freerdp/source"
BUILD_DIR="${PROJECT_ROOT}/src/bin/freerdp/build"
INSTALL_DIR="${PROJECT_ROOT}/src/bin/freerdp/install"
BIN_DIR="${PROJECT_ROOT}/src/bin/freerdp/${OS}/${ARCH}"

########################################################
# Install build dependencies
########################################################

if [[ "$OS" == "linux" ]]; then
    echo "==> Installing build dependencies (requires sudo)..."
    sudo apt update
    sudo apt install -y \
        build-essential \
        git \
        cmake \
        ninja-build \
        pkg-config \
        libssl-dev \
        libx11-dev \
        libxext-dev \
        libxinerama-dev \
        libxkbfile-dev \
        libxrandr-dev \
        libxi-dev \
        libxcursor-dev \
        libxv-dev \
        libcups2-dev \
        libasound2-dev \
        libpulse-dev \
        libusb-1.0-0-dev \
        libudev-dev \
        libpcsclite-dev \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libv4l-dev
    echo
else
    echo "==> Skipping automatic dependency installation (OS=${OS})."
    echo "    Make sure you have all required libs installed via Homebrew or your package manager."
    echo
fi

########################################################
# Clone or update FreeRDP source
########################################################

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "==> Cloning FreeRDP source into $SOURCE_DIR..."
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$SOURCE_DIR"
else
    echo "==> FreeRDP source already exists in $SOURCE_DIR, pulling latest changes..."
    git -C "$SOURCE_DIR" pull
fi

########################################################
# Verify source, build, install & bin directories
########################################################

if [[ ! -f "$SOURCE_DIR/CMakeLists.txt" ]]; then
    echo "ERROR: Could not find CMakeLists.txt in '$SOURCE_DIR'."
    exit 1
fi

if [[ -d "$BUILD_DIR" ]]; then
    rm -rf "$BUILD_DIR"
fi
mkdir -p "${BUILD_DIR}"

if [[ ! -d "$BIN_DIR" ]]; then
    mkdir -p "${BIN_DIR}"
fi

if [[ ! -d "$INSTALL_DIR" ]]; then
    mkdir -p "${INSTALL_DIR}"
fi

echo "==> Source dir : ${SOURCE_DIR}"
echo "==> Build dir  : ${BUILD_DIR}"
echo "==> Install to : ${INSTALL_DIR}"
echo "==> Bin root : ${BIN_DIR}"
echo

########################################################
# Configure with CMake (out-of-tree)
########################################################

echo "==> Configuring FreeRDP with USB + audio + RDPECAM..."

cmake -G "Ninja" \
  -B "${BUILD_DIR}" \
  -S "${SOURCE_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}" \
  \
  -DWITH_ALSA=ON \
  -DWITH_PULSE=ON \
  \
  -DWITH_FFMPEG=ON \
  -DWITH_DSP_FFMPEG=ON \
  \
  -DWITH_CHANNELS=ON \
  -DWITH_CLIENT=ON \
  -DWITH_SERVER=OFF \
  \
  -DWITH_URBDRC=ON \
  -DWITH_LIBUSB=ON \
  -DWITH_UDEV=ON \
  -DCHANNEL_URBDRC=ON \
  -DCHANNEL_URBDRC_CLIENT=ON \
  \
  -DWITH_GSTREAMER=ON \
  -DWITH_GSTREAMER_1_0=ON \
  \
  -DWITH_V4L=ON \
  -DCHANNEL_RDPECAM_CLIENT=ON

echo

########################################################
# Build & install
########################################################

echo "==> Building FreeRDP (this may take a while)..."
cmake --build "${BUILD_DIR}" --target all

echo "==> Installing FreeRDP to $INSTALL_DIR..."
cmake --build "${BUILD_DIR}" --target install

echo

########################################################
# Copy built files into bin directory
########################################################

echo "==> Copying files..."

BIN_DEST="$BIN_DIR"
LIB_DEST="$BIN_DIR/lib"
PLUGIN_DEST="$BIN_DIR/plugins"

mkdir -p "$LIB_DEST" "$PLUGIN_DEST"

echo "  - Copying xfreerdp..."
cp "${INSTALL_DIR}/bin/xfreerdp" "${BIN_DEST}/"

echo "  - Copying core libraries..."
cp "${INSTALL_DIR}/lib/"libfreerdp* "${LIB_DEST}/" 2>/dev/null || true
cp "${INSTALL_DIR}/lib/"libwinpr* "${LIB_DEST}/" 2>/dev/null || true

echo "  - Copying client plugins..."
# For FreeRDP 3, plugins live in lib/freerdp3
if [[ -d "${INSTALL_DIR}/lib/freerdp3" ]]; then
    cp "${INSTALL_DIR}/lib/freerdp3/"* "${PLUGIN_DEST}/" 2>/dev/null || true
fi

echo "==> Copy complete."
echo "    xfreerdp : ${BIN_DEST}/xfreerdp"
echo "    libs     : ${LIB_DEST}"
echo "    plugins  : ${PLUGIN_DEST}"
echo

########################################################
# Test results: version, buildconfig & capabilities
########################################################

echo "==> Running basic tests on the built xfreerdp..."
echo

if [[ -x "${BIN_DEST}/xfreerdp" ]]; then
    echo "  [1] Version:"
    "${BIN_DEST}/xfreerdp" /version || true
    echo

    echo "  [2] Build configuration (full):"
    "${BIN_DEST}/xfreerdp" /buildconfig || true
    echo

    echo "  [3] Build configuration (filtered for interesting flags):"
    "${BIN_DEST}/xfreerdp" /buildconfig 2>/dev/null | \
        grep -E 'WITH_(ALSA|PULSE|URBDRC|LIBUSB|UDEV|GSTREAMER|FFMPEG|V4L|RDPECAM)' || true
    echo

    echo "  [4] Installed client plugins:"
    ls -1 "${PLUGIN_DEST}" || true
    echo

    echo "  [5] Linked libraries for xfreerdp (ldd):"
    if command -v ldd >/dev/null 2>&1; then
        ldd "${BIN_DEST}/xfreerdp" || true
    else
        echo "ldd not available on this system."
    fi
    echo
else
    echo "ERROR: ${BIN_DEST}/xfreerdp is missing or not executable."
    exit 1
fi

########################################################
# Done
########################################################

echo "==> Done."
echo
