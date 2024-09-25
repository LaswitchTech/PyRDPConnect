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
SPEC_FILE="client.spec"
ICON_FILE="src/icons/icon.icns"

if [ ! -f "$SPEC_FILE" ]; then
    log ".spec file not found. Generating a new one with PyInstaller..."
    if [ "$OS" == "macos" ]; then
        pyinstaller --windowed --name "$NAME" src/client.py
    elif [ "$OS" == "linux" ]; then
        pyinstaller --onefile --name "$NAME" src/client.py
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

# Copy necessary directories into the app bundle or executable directory
if [ "$OS" == "macos" ]; then
    APP_BUNDLE="dist/client.app/Contents/Resources"

    log "Copying resources into the app bundle..."
    mkdir -p "$APP_BUNDLE/styles"
    mkdir -p "$APP_BUNDLE/img"
    mkdir -p "$APP_BUNDLE/icons"

    cp -R src/styles/* "$APP_BUNDLE/styles/"
    cp -R src/img/* "$APP_BUNDLE/img/"
    cp -R src/icons/* "$APP_BUNDLE/icons/"
else
    EXEC_DIR="dist/client"

    log "Copying resources into the executable directory..."
    mkdir -p "$EXEC_DIR/styles"
    mkdir -p "$EXEC_DIR/img"
    mkdir -p "$EXEC_DIR/icons"

    cp -R src/styles/* "$EXEC_DIR/styles/"
    cp -R src/img/* "$EXEC_DIR/img/"
    cp -R src/icons/* "$EXEC_DIR/icons/"
fi

# Copy the appropriate FreeRDP binary based on the OS
log "Copying FreeRDP binary for $OS..."
mkdir -p "src/freerdp/$OS"
FREERDP_PATH=$(whereis xfreerdp | awk '{ print $2 }')

if [ ! -f "src/freerdp/$OS/xfreerdp" ]; then
    if [ -f "$FREERDP_PATH" ]; then
        cp "$FREERDP_PATH" "src/freerdp/$OS/xfreerdp"
    else
        log "Unable to find the FreeRDP binary at $FREERDP_PATH. Exiting."
        exit 1
    fi
fi

if [ "$OS" == "macos" ]; then
    log "Copying FreeRDP binary into the app bundle..."
    mkdir -p "$APP_BUNDLE/freerdp"
    cp "src/freerdp/$OS/xfreerdp" "$APP_BUNDLE/freerdp/"
else
    log "Copying FreeRDP binary into the executable directory..."
    mkdir -p "$EXEC_DIR/freerdp"
    cp "src/freerdp/$OS/xfreerdp" "$EXEC_DIR/freerdp/"
fi

log "Build completed successfully."

# Deactivate the virtual environment
deactivate
