#!/bin/bash

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

# --- Require python3.13 on PATH ---
PYTHON_BIN="$(command -v python3.13 || true)"
if [ -z "$PYTHON_BIN" ]; then
  log "python3.13 not found. On macOS, run: brew install python@3.13"
  exit 1
fi

# --- (Re)create venv if missing or wrong version ---
NEED_RECREATE=0
if [ ! -x "env/bin/python" ]; then
  NEED_RECREATE=1
else
  VENV_VER="$(env/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' || echo unknown)"
  if [ "$VENV_VER" != "3.13" ]; then
    NEED_RECREATE=1
  fi
fi

if [ "$NEED_RECREATE" -eq 1 ]; then
  log "Creating fresh Python 3.13 virtual environment..."
  rm -rf env
  "$PYTHON_BIN" -m venv env
fi

# --- Activate venv ---
# shellcheck disable=SC1091
source env/bin/activate

# --- Double-check version (hard fail if not 3.13) ---
ACTIVE_VER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$ACTIVE_VER" != "3.13" ]; then
  log "Active Python is $ACTIVE_VER, expected 3.13. Aborting."
  exit 1
fi
log "Using Python $(python -V)"

# Ensure that pip is updated
log "Updating pip..."
python -m pip install --upgrade pip wheel

log "Installing build dependencies..."
# PyInstaller 6.9+ supports 3.13 well; lock to <7 to avoid future surprizes.
# PyQt5 5.15.x is stable for Qt5 on macOS/Linux; lock <6.
python -m pip install "pyinstaller>=6.9,<7" "sip>=6.9,<7" "PyQt5>=5.15,<6"

# Optional tools you had; keeping them only if you need them:
python -m pip install importlib PySide6-Addons

# # Ensure the necessary packages are installed
# log "Installing required packages..."
# pip install pyinstaller sip importlib PySide6-Addons
# pip install pyqt5 --config-settings --confirm-license= --verbose

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
        datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img'), ('src/freerdp/$OS/xfreerdp', 'xfreerdp')],
    " $SPEC_FILE
elif [ "$OS" == "linux" ]; then
    sed -i "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE
    sed -i "/Analysis/s/(.*)/\0, hiddenimports=['PyQt5.QtSvg']/" $SPEC_FILE
    sed -i "/a.datas +=/a \\
        datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img'), ('src/freerdp/$OS/xfreerdp', 'xfreerdp')],
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
    APP_FRAMEWORKS="$APP_ROOT/Frameworks"

    log "Creating app resource directories..."
    mkdir -p "$APP_RES/styles" "$APP_RES/img" "$APP_RES/icons"
    mkdir -p "$APP_MACOS" "$APP_FRAMEWORKS/freerdp"

    log "Copying UI resources..."
    cp -R src/styles/* "$APP_RES/styles/"
    cp -R src/img/*    "$APP_RES/img/"
    cp -R src/icons/*  "$APP_RES/icons/"

    log "Copying FreeRDP binary..."
    cp "src/freerdp/macos/xfreerdp" "$APP_MACOS/"
    chmod +x "$APP_MACOS/xfreerdp"

    log "Copying FreeRDP dylibs..."
    # make sure you’ve pre-copied Homebrew’s dylibs into your repo at src/freerdp/macos/lib
    # e.g.: cp /opt/homebrew/Cellar/freerdp/*/lib/*.dylib src/freerdp/macos/lib/
    cp src/freerdp/macos/lib/*.dylib "$APP_FRAMEWORKS/freerdp/"

    FREERDP_BIN="$APP_MACOS/xfreerdp"
    LIB_DIR="@executable_path/../Frameworks/freerdp"

    log "Patching rpaths on xfreerdp..."
    # allow dyld to search our Frameworks/freerdp folder
    install_name_tool -add_rpath "$LIB_DIR" "$FREERDP_BIN" || true

    log "Rewriting dylib IDs to @rpath/NAME..."
    for dylib in "$APP_FRAMEWORKS"/freerdp/*.dylib; do
        base="$(basename "$dylib")"
        install_name_tool -id "@rpath/$base" "$dylib"
    done

    log "Rewriting internal dylib references (libs -> @rpath/NAME)..."
    for dylib in "$APP_FRAMEWORKS"/freerdp/*.dylib; do
        # find any absolute /opt/homebrew/Cellar/freerdp/... refs and replace
        while IFS= read -r dep; do
        base="$(basename "$dep")"
        install_name_tool -change "$dep" "@rpath/$base" "$dylib"
        done < <(otool -L "$dylib" | awk '/\/opt\/homebrew\/Cellar\/freerdp/ {print $1}')
    done

    log "Rewriting references inside xfreerdp..."
    while IFS= read -r dep; do
        base="$(basename "$dep")"
        install_name_tool -change "$dep" "@rpath/$base" "$FREERDP_BIN"
    done < <(otool -L "$FREERDP_BIN" | awk '/\/opt\/homebrew\/Cellar\/freerdp/ {print $1}')

    # (Optional) Verify:
    log "Verifying linkage:"
    otool -L "$FREERDP_BIN" | sed 's/^/  /'
else
    log "Linux build does not require copying resources to a separate directory, as it is a single-file executable."

    # Note: If you need to bundle resources within the executable, adjust the PyInstaller options to include those resources
fi

# Create a directory to store the final output based on the OS
FINAL_DIR="dist/$OS"
if [ -d "$FINAL_DIR" ]; then
    rm -rf "$FINAL_DIR"
fi
mkdir -p "$FINAL_DIR"

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
