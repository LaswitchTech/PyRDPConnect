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

# Check if the Python virtual environment is already set up
if [ ! -f "env/bin/python" ] || [ ! -f "env/bin/python3" ] || [ ! -f "env/bin/pip" ]; then
    log "Python virtual environment not found. Creating a new one..."
    python3 -m venv env
else
    log "Python virtual environment found."
fi

# Activate the environment
source env/bin/activate

# Ensure that pip is updated
log "Updating pip..."
python -m pip install --upgrade pip

# Ensure the necessary packages are installed
log "Installing required packages..."
pip install pyinstaller sip importlib PySide6-Addons
pip install pyqt5 --config-settings --confirm-license=

# Check if the .spec file exists
SPEC_FILE="$NAME.spec"
ICON_FILE="src/icons/icon.icns"

if [ ! -f "$SPEC_FILE" ]; then
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
fi

# Update the .spec file to include the custom icon and data files
log "Updating the .spec file to include the custom icon and data files..."
if [ "$OS" == "macos" ]; then
    sed -i '' "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE
    sed -i '' "/a.datas +=/a \\
        datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img'), ('src/freerdp/$OS/xfreerdp', 'xfreerdp')],
    " $SPEC_FILE
elif [ "$OS" == "linux" ]; then
    sed -i "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE
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
log "Moving the application or executable to the appropriate directory..."
if [ "$OS" == "macos" ]; then
    log "Moving the .app bundle to the $FINAL_DIR directory..."
    mv "dist/$NAME.app" "$FINAL_DIR/"
else
    log "Moving the executable to the $FINAL_DIR directory..."
    mv "dist/$NAME" "$FINAL_DIR/"
fi

# Cleanup: Remove the leftover dist/$NAME directory on macOS
log "Cleaning up..."
if [ "$OS" == "macos" ]; then
    log "Cleaning up the dist directory..."
    rm -rf "dist/$NAME"
fi

log "Build completed successfully."

# Deactivate the virtual environment
deactivate
