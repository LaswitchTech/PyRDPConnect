#!/usr/bin/env bash
# Rebuild FreeRDP 3.x with USB + audio support for PyRDPConnect (Pi)
# Can be dropped in either the FreeRDP source root *or* the build directory.

set -euo pipefail

########################################
# Configurable variables
########################################

# Where to "install" this custom FreeRDP build
PREFIX="${PREFIX:-$HOME/freerdp-arm64-install}"

# Where your PyRDPConnect Freerdp bundle lives on the Pi.
# Override with:  PYRDP_ROOT=/path/to/src/bin/freerdp/linux/arm64 ./rebuild_freerdp_pyrdp.sh
PYRDP_ROOT="${PYRDP_ROOT:-$HOME/PyRDPConnect/src/bin/freerdp/linux/arm64}"

########################################
# Locate source & build directories
########################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/CMakeLists.txt" ]]; then
    # Script is in FreeRDP source root
    SRCDIR="$SCRIPT_DIR"
    BUILDDIR="$SRCDIR/build"
    mkdir -p "$BUILDDIR"
else
    # Assume script is in build dir: ../ should be the source root
    BUILDDIR="$SCRIPT_DIR"
    SRCDIR="$SCRIPT_DIR/.."
    if [[ ! -f "$SRCDIR/CMakeLists.txt" ]]; then
        echo "ERROR: Could not find CMakeLists.txt in '$SRCDIR'."
        echo "Drop this script either in the FreeRDP source root, or in its 'build' directory."
        exit 1
    fi
fi

echo "==> Source dir : $SRCDIR"
echo "==> Build dir  : $BUILDDIR"
echo "==> Install to : $PREFIX"
echo "==> PyRDP root : $PYRDP_ROOT (will copy here only if directory exists)"
echo

########################################
# Install build dependencies
########################################

echo "==> Installing build dependencies (requires sudo)..."
sudo apt update
sudo apt install -y \
  build-essential git cmake ninja-build pkg-config \
  libssl-dev libx11-dev libxext-dev libxinerama-dev libxkbfile-dev \
  libxrandr-dev libxi-dev libxcursor-dev libxv-dev libcups2-dev \
  libasound2-dev libpulse-dev \
  libusb-1.0-0-dev libudev-dev \
  libpcsclite-dev \
  libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev

echo

########################################
# Clean old CMake cache (but keep directory & script)
########################################

cd "$BUILDDIR"
echo "==> Cleaning old CMake cache..."
rm -f CMakeCache.txt
rm -rf CMakeFiles

########################################
# Configure with CMake
########################################

echo "==> Configuring FreeRDP with USB + audio..."

cmake -G "Ninja" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
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
  "$SRCDIR"

echo

########################################
# Build & install
########################################

echo "==> Building FreeRDP (this may take a while)..."
ninja

echo "==> Installing FreeRDP to $PREFIX..."
ninja install

echo

########################################
# Show build configuration summary
########################################

echo "==> Verifying build configuration..."
"$PREFIX/bin/xfreerdp" /buildconfig | \
  grep -E 'WITH_(ALSA|PULSE|URBDRC|LIBUSB|UDEV|GSTREAMER|FFMPEG)' || true

echo

########################################
# Optional: copy into PyRDPConnect bundle
########################################

if [[ -d "$PYRDP_ROOT" ]]; then
    echo "==> PyRDPConnect bundle directory exists, copying files..."

    BIN_DEST="$PYRDP_ROOT"
    LIB_DEST="$PYRDP_ROOT/lib"
    PLUGIN_DEST="$PYRDP_ROOT/plugins"

    mkdir -p "$LIB_DEST" "$PLUGIN_DEST"

    echo "  - Copying xfreerdp..."
    cp "$PREFIX/bin/xfreerdp" "$BIN_DEST/"

    echo "  - Copying core libraries..."
    # libfreerdp*, libwinpr*, etc.
    cp "$PREFIX/lib/"libfreerdp* "$LIB_DEST/" 2>/dev/null || true
    cp "$PREFIX/lib/"libwinpr* "$LIB_DEST/" 2>/dev/null || true

    echo "  - Copying client plugins..."
    # For FreeRDP 3, plugins live in lib/freerdp3
    if [[ -d "$PREFIX/lib/freerdp3" ]]; then
        cp "$PREFIX/lib/freerdp3/"* "$PLUGIN_DEST/" 2>/dev/null || true
    fi

    echo "==> Copy complete."
    echo "    xfreerdp       : $BIN_DEST/xfreerdp"
    echo "    libs           : $LIB_DEST"
    echo "    plugins        : $PLUGIN_DEST"
else
    echo "==> NOTE: PyRDPConnect bundle directory '$PYRDP_ROOT' does not exist."
    echo "    Skipping copy step."
    echo "    You can manually copy from:"
    echo "      $PREFIX/bin/xfreerdp"
    echo "      $PREFIX/lib/ (libfreerdp*, libwinpr*)"
    echo "      $PREFIX/lib/freerdp3/ (plugins)"
fi

echo
echo "==> Done."
echo "Make sure your PyRDPConnect freerdp.py is using:"
echo "  - LD_LIBRARY_PATH=\$PYRDP_ROOT/lib"
echo "  - FREERDP_PLUGIN_PATH=\$PYRDP_ROOT/plugins"
