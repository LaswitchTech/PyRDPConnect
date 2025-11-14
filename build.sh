#!/bin/bash
set -euo pipefail

# Function to print messages with a timestamp
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1"
}

# Function to detect the operating system
detect_os() {
    case "$(uname -s)" in
        Darwin)
            echo "macos"
            ;;
        Linux)
            echo "linux"
            ;;
        *)
            echo "unsupported"
            ;;
    esac
}

# Set the name of the application
NAME="PyRDPConnect"

# Determine the operating system
OS=$(detect_os)

if [ "$OS" == "unsupported" ]; then
    log "Unsupported operating system. Exiting."
    exit 1
fi

# Determine arch and whether we should use system PyQt5 (APT) on Linux ARM
ARCH="$(uname -m)"
USE_SYSTEM_PYQT=0
if [ "$OS" = "linux" ] && { [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "armv7l" ] || [ "$ARCH" = "armhf" ]; }; then
    USE_SYSTEM_PYQT=1
fi

# Create a directory to store the final output based on the OS
FINAL_DIR="dist/$OS"
if [ -d "$FINAL_DIR" ]; then
    rm -rf "$FINAL_DIR"
fi
mkdir -p "$FINAL_DIR"

# Require python3.11 on PATH
PYTHON_BIN="$(command -v python3.11 || true)"
if [ -z "$PYTHON_BIN" ]; then
  log "python3.11 not found. On macOS, run: brew install python@3.11"
  exit 1
fi

# (Re)create venv if missing or wrong version
NEED_RECREATE=0
if [ ! -x "env/bin/python" ]; then
  NEED_RECREATE=1
else
  VENV_VER="$(env/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' || echo unknown)"
  if [ "$VENV_VER" != "3.11" ]; then
    NEED_RECREATE=1
  fi
fi

if [ "$NEED_RECREATE" -eq 1 ]; then
    log "Creating fresh Python 3.11 virtual environment..."
    rm -rf env
    if [ "$USE_SYSTEM_PYQT" -eq 1 ]; then
        # allow APT-installed PyQt5 to be visible in the venv
        "$PYTHON_BIN" -m venv --system-site-packages env
    else
        "$PYTHON_BIN" -m venv env
    fi
fi

# --- Activate venv ---
# shellcheck disable=SC1091
source env/bin/activate

# --- Double-check version (hard fail if not 3.11) ---
ACTIVE_VER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$ACTIVE_VER" != "3.11" ]; then
  log "Active Python is $ACTIVE_VER, expected 3.11. Aborting."
  exit 1
fi
log "Using Python $(python -V)"

# Ensure that pip is updated
log "Updating pip..."
python -m pip install --upgrade pip wheel

log "Installing build dependencies..."
# PyInstaller 6.9+ supports 3.11 well; lock to <7 to avoid future surprizes.
# PyQt5 5.15.x is stable for Qt5 on macOS/Linux; lock <6.
python -m pip install "pyinstaller>=6.9,<7" "sip>=6.9,<7"

if [ "$USE_SYSTEM_PYQT" -eq 1 ]; then
    # Ensure system PyQt5 (and QtSvg) are present
    if command -v apt-get >/dev/null 2>&1; then
        log "Installing system PyQt5 via APT (requires sudo)..."
        sudo apt-get update
        sudo apt-get install -y python3-pyqt5 python3-pyqt5.qtsvg
    else
        log "ERROR: APT not found; cannot install system PyQt5. Install PyQt5 manually or switch to a distro with APT."
        exit 1
    fi
#     # Sanity check
#     python - <<'PY'
# try:
#     import PyQt5.QtCore, PyQt5.QtWidgets, PyQt5.QtSvg
#     print("OK: System PyQt5 detected.")
# except Exception as e:
#     raise SystemExit(f"PyQt5 missing after APT install: {e}")
# PY
else
    # Non-ARM / macOS etc: keep using PyPI wheels
    python -m pip install "PyQt5>=5.15,<6"
fi

# Optional tools you had; keeping them only if you need them:
python -m pip install importlib PySide6-Addons

# Check if the .spec file exists
SPEC_FILE="$NAME.spec"
ICON_FILE="src/icons/icon.icns"

# Cleanup: Remove the leftover dist/$NAME directory on macOS
log "Cleaning up..."
if [ -d "dist/$NAME" ]; then
    rm -rf "dist/$NAME"
fi
if [ -f "$SPEC_FILE" ]; then
    rm -f "$SPEC_FILE"
fi

log "Verifying required PyQt5 modules are present..."
python - <<'PY'
from importlib.util import find_spec
missing = [m for m in ("PyQt5", "PyQt5.QtSvg") if find_spec(m) is None]
if missing:
    raise SystemExit(f"Missing modules before build: {missing}")
print("Qt check passed.")
PY

log ".spec file not found. Generating a new one with PyInstaller..."
if [ "$OS" == "macos" ]; then
    pyinstaller --windowed --name "$NAME" src/PyRDPConnect.py
elif [ "$OS" == "linux" ]; then
    pyinstaller --onefile --name "$NAME" src/PyRDPConnect.py
fi

# Ensure the spec file now exists
if [ ! -f "$SPEC_FILE" ]; then
    log "Failed to create .spec file. Exiting."
    exit 1
fi

log "Generated .spec file: $SPEC_FILE"

# Update the .spec file to include the custom icon, data files, and hidden imports
log "Updating the .spec file to include the custom icon, data files, and hidden imports..."
if [ "$OS" == "macos" ]; then
    sed -i '' "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE
    sed -i '' "/Analysis/s/(.*)/\0, hiddenimports=['PyQt5.QtSvg']/" $SPEC_FILE
    sed -i '' "/a.datas +=/a \\
        datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img')],
    " $SPEC_FILE
elif [ "$OS" == "linux" ]; then
    sed -i "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE
    sed -i "/Analysis/s/(.*)/\0, hiddenimports=['PyQt5.QtSvg']/" $SPEC_FILE
    sed -i "/a.datas +=/a \\
        datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img')],
    " $SPEC_FILE
fi

# Build the project with PyInstaller using the updated .spec file
log "Building the project with PyInstaller..."
pyinstaller --noconfirm $SPEC_FILE

# Copy resources into the appropriate location
if [ "$OS" == "macos" ]; then
    APP_ROOT="dist/$NAME.app/Contents"
    APP_MACOS="$APP_ROOT/MacOS"
    APP_RES="$APP_ROOT/Resources"

    log "Creating app resource directories..."
    mkdir -p "$APP_RES/styles" "$APP_RES/img" "$APP_RES/icons"
    cp -R src/styles/* "$APP_RES/styles/"
    cp -R src/img/*    "$APP_RES/img/"
    cp -R src/icons/*  "$APP_RES/icons/"

    # ---- Bundle FreeRDP as PyRDPConnect expects (Resources/freerdp/macos/...) ----
    VENDOR_DIR_SRC="src/freerdp/macos"
    VENDOR_DIR_DST="$APP_RES/freerdp/macos"
    mkdir -p "$VENDOR_DIR_DST"
    log "Copying FreeRDP tree to Resources..."
    rsync -a "$VENDOR_DIR_SRC/" "$VENDOR_DIR_DST/"

    FREERDP_BIN="$VENDOR_DIR_DST/xfreerdp"
    LIB_DIR="$VENDOR_DIR_DST/lib"
    X11_DIR="$VENDOR_DIR_DST/x11"        # optional (if you vendored X11 libs)
    PLUGINS_DIR="$VENDOR_DIR_DST/plugins" # optional

    chmod +x "$FREERDP_BIN"

    # ---- Patch rpaths + rewrite absolute Homebrew refs -> @rpath/<name> ----
    BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"

    add_rpath_if_missing() {
      local bin="$1" r="$2"
      if ! otool -l "$bin" | awk '/LC_RPATH/{getline; print $2}' | grep -qx "$r"; then
        install_name_tool -add_rpath "$r" "$bin" 2>/dev/null || true
      fi
    }

    # We want dyld to look inside ../lib and ../x11 relative to xfreerdp
    add_rpath_if_missing "$FREERDP_BIN" "@loader_path/../lib"
    if [ -d "$X11_DIR" ]; then
      add_rpath_if_missing "$FREERDP_BIN" "@loader_path/../x11"
    fi

    # For each lib we ship, set id to @rpath/<base> and rewrite any Homebrew absolute deps to @rpath/<base>
    patch_one_file() {
      local file="$1"
      # set its own id (for dylibs)
      if [[ "$file" == *.dylib ]]; then
        install_name_tool -id "@rpath/$(basename "$file")" "$file" 2>/dev/null || true
      fi
      # rewrite deps
      otool -L "$file" | awk 'NR>1{print $1}' | while read -r dep; do
        [ -z "$dep" ] && continue
        case "$dep" in
          /System/*|/usr/lib/*) continue ;;             # keep system libs
        esac
        if echo "$dep" | grep -Eq "^$BREW_PREFIX/(opt|Cellar)/"; then
          base="$(basename "$dep")"
          install_name_tool -change "$dep" "@rpath/$base" "$file" 2>/dev/null || true
        fi
      done
    }

    log "Patching bundled dylibs..."
    if [ -d "$LIB_DIR" ]; then
      find "$LIB_DIR" -type f -name "*.dylib" -print0 | while IFS= read -r -d '' f; do
        chmod u+w "$f"
        patch_one_file "$f"
      done
    fi
    if [ -d "$X11_DIR" ]; then
      find "$X11_DIR" -type f -name "*.dylib" -print0 | while IFS= read -r -d '' f; do
        chmod u+w "$f"
        patch_one_file "$f"
      done
    fi

    log "Patching xfreerdp to use @rpath for Homebrew deps..."
    patch_one_file "$FREERDP_BIN"

    # Ad-hoc sign so dyld doesn’t complain
    log "Ad-hoc codesigning bundled libs and app..."
    if [ -d "$LIB_DIR" ]; then
      find "$LIB_DIR" -type f -name "*.dylib" -exec codesign --force --timestamp=none -s - {} \;
    fi
    if [ -d "$X11_DIR" ]; then
      find "$X11_DIR" -type f -name "*.dylib" -exec codesign --force --timestamp=none -s - {} \;
    fi
    [ -f "$FREERDP_BIN" ] && codesign --force --timestamp=none -s - "$FREERDP_BIN"
    codesign --force --deep --timestamp=none -s - "dist/$NAME.app"

    log "Verify xfreerdp linkage (should show @rpath -> ../lib and ../x11):"
    otool -L "$FREERDP_BIN" | sed 's/^/  /'
else
    log "Moving the executable to the $FINAL_DIR directory..."
    mv "dist/$NAME" "$FINAL_DIR/"

    # ---- Place bundled FreeRDP under dist/linux/src/freerdp/linux/... ----
    LNX_VENDOR_SRC="src/freerdp/linux"
    LNX_VENDOR_DST="$FINAL_DIR/src/freerdp/linux"
    if [ -d "$LNX_VENDOR_SRC" ]; then
      log "Copying FreeRDP tree to $LNX_VENDOR_DST ..."
      mkdir -p "$(dirname "$LNX_VENDOR_DST")"
      rsync -a "$LNX_VENDOR_SRC/" "$LNX_VENDOR_DST/"
      chmod +x "$LNX_VENDOR_DST/xfreerdp" || true
      FREERDP_BIN="$LNX_VENDOR_DST/xfreerdp"    # <— ADD THIS LINE
    else
      log "WARN: $LNX_VENDOR_SRC not found; build will fall back to system xfreerdp at runtime."
    fi
fi

# Verify the vendored version (macOS and linux)
expect_major="3"   # adjust if you vendor 2.x
if [ -x "$FREERDP_BIN" ]; then
    vend_ver="$("$FREERDP_BIN" +version 2>/dev/null | head -n1 | grep -Eo '[0-9]+\.[0-9]+(\.[0-9]+)?' || true)"
    if [ -z "$vend_ver" ]; then
        log "WARN: Could not detect vendored FreeRDP version from +version"
    else
        vmaj="${vend_ver%%.*}"
        if [ "$vmaj" != "$expect_major" ]; then
            log "ERROR: Vendored FreeRDP major version is $vmaj, expected $expect_major"
            exit 1
        fi
        log "Vendored FreeRDP version: $vend_ver"
    fi
fi

# On Linux, fail fast if vendored xfreerdp has unresolved deps
if [ "$OS" = "linux" ] && [ -x "${FREERDP_BIN:-}" ]; then
  if command -v ldd >/dev/null 2>&1; then
    if ldd "$FREERDP_BIN" | grep -q "not found"; then
      log "ERROR: Missing shared libraries for vendored xfreerdp:"
      ldd "$FREERDP_BIN" | grep "not found" || true
      exit 1
    fi
  else
    log "WARN: ldd not available; skipping shared-library check."
  fi
fi

# Move the built application or executable to the appropriate directory
if [ "$OS" == "macos" ]; then
    log "Moving the .app bundle to the $FINAL_DIR directory..."
    mv "dist/$NAME.app" "$FINAL_DIR/"

    # Create a DMG image
    log "Creating a DMG image for macOS..."
    DMG_NAME="$FINAL_DIR/$NAME.dmg"
    hdiutil create "$DMG_NAME" -volname "$NAME" -srcfolder "$FINAL_DIR/$NAME.app" -ov -format UDZO

    log "DMG image created at $DMG_NAME"
else
    log "Moving the executable to the $FINAL_DIR directory..."
    mv "dist/$NAME" "$FINAL_DIR/"
fi

# Cleanup: Remove the leftover dist/$NAME directory on macOS
if [ -d "dist/$NAME" ]; then
    log "Cleaning up the dist directory..."
    rm -rf "dist/$NAME"
fi

log "Build completed successfully."

# Deactivate the virtual environment
deactivate
