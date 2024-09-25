#!/bin/bash

# Function to print messages with a timestamp
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1"
}

# Check if the Python virtual environment is already set up
if [ ! -f "env/bin/python" ] || [ ! -f "env/bin/python3" ] || [ ! -f "env/bin/pip" ]; then
    log "Python virtual environment not found. Creating a new one..."
    python3 -m venv env
else
    log "Python virtual environment found."
fi

# Activate the environment
source env/bin/activate

# Ensure the necessary packages are installed
log "Installing required packages..."
pip install pyinstaller sip importlib pyqt5 PySide6-Addons

# Check if the .spec file exists
SPEC_FILE="client.spec"
ICON_FILE="src/icons/icon.icns"

if [ ! -f "$SPEC_FILE" ]; then
    log ".spec file not found. Generating a new one with PyInstaller..."
    pyinstaller --onefile --windowed --name client src/client.py

    # Ensure the spec file now exists
    if [ ! -f "$SPEC_FILE" ]; then
        log "Failed to create .spec file. Exiting."
        exit 1
    fi

    log "Generated .spec file: $SPEC_FILE"
fi

# Update the .spec file to include the custom icon and data files
log "Updating the .spec file to include the custom icon and data files..."
sed -i '' "s|icon=None|icon='$ICON_FILE'|g" $SPEC_FILE

# Ensure that styles, icons, img, and FreeRDP binary are included in the app bundle
sed -i '' "/a.datas +=/a \\
    datas=[('src/styles', 'styles'), ('src/icons', 'icons'), ('src/img', 'img'), ('/usr/local/bin/xfreerdp', 'xfreerdp')],
" $SPEC_FILE

# Build the project with PyInstaller using the updated .spec file
log "Building the project with PyInstaller..."
pyinstaller --noconfirm $SPEC_FILE

# Copy necessary directories into the app bundle
APP_BUNDLE="dist/client.app/Contents/Resources"

log "Copying resources into the app bundle..."
mkdir -p "$APP_BUNDLE/styles"
mkdir -p "$APP_BUNDLE/img"
mkdir -p "$APP_BUNDLE/icons"

cp -R src/styles/* "$APP_BUNDLE/styles/"
cp -R src/img/* "$APP_BUNDLE/img/"
cp -R src/icons/* "$APP_BUNDLE/icons/"

log "Copying FreeRDP binary into the app bundle..."
mkdir -p "$APP_BUNDLE/freerdp"
if [ -f "/opt/homebrew/bin/xfreerdp" ]; then
    cp /opt/homebrew/bin/xfreerdp "$APP_BUNDLE/freerdp/"
else
    if [ -f "/opt/homebrew/bin/xfreerdp" ]; then
        cp /usr/local/bin/xfreerdp "$APP_BUNDLE/freerdp/"
    else
        log "Unable to copy FreeRDP binary into the app bundle"
    fi
fi

log "Build completed successfully."

# Deactivate the virtual environment
deactivate
