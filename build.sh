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
    APP_BUNDLE="dist/$NAME.app/Contents/Resources"

    log "Copying resources into the app bundle..."
    mkdir -p "$APP_BUNDLE/styles"
    mkdir -p "$APP_BUNDLE/img"
    mkdir -p "$APP_BUNDLE/icons"

    cp -R src/styles/* "$APP_BUNDLE/styles/"
    cp -R src/img/* "$APP_BUNDLE/img/"
    cp -R src/icons/* "$APP_BUNDLE/icons/"

    log "Copying FreeRDP binary into the app bundle..."
    mkdir -p "$APP_BUNDLE/freerdp/$OS"
    cp "src/freerdp/$OS/xfreerdp" "$APP_BUNDLE/freerdp/$OS/"

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
