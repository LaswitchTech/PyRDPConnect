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

# Build the project with PyInstaller
log "Building the project with PyInstaller..."
pyinstaller --noconfirm --onefile --windowed src/client.py

# Copy necessary directories into the app bundle
APP_BUNDLE="dist/client.app/Contents/Resources"

log "Copying resources into the app bundle..."
mkdir -p "$APP_BUNDLE/styles"
mkdir -p "$APP_BUNDLE/img"
mkdir -p "$APP_BUNDLE/icons"

cp -R src/styles/* "$APP_BUNDLE/styles/"
cp -R src/img/* "$APP_BUNDLE/img/"
cp -R src/icons/* "$APP_BUNDLE/icons/"

log "Build completed successfully."

# Deactivate the virtual environment
deactivate
