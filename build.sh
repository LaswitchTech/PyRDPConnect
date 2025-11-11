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

    # ---- BEGIN: Bundle X11 stack + add rpath + ad-hoc sign (Bash 3.2-safe) ----
    X11_DIR="$APP_FRAMEWORKS/x11"
    mkdir -p "$X11_DIR"

    # Discover Homebrew prefix (Apple Silicon=/opt/homebrew; Intel=/usr/local)
    BREW_PREFIX="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
    X11_VENDOR_DIR="src/freerdp/macos/x11"

    # Direct X11 deps that xfreerdp links against (seed set)
    REQUIRED_X11=(
      "libX11.6.dylib"
      "libXext.6.dylib"
      "libXinerama.1.dylib"
      "libXcursor.1.dylib"
      "libXv.1.dylib"
      "libXi.6.dylib"
      "libXrender.1.dylib"
      "libXrandr.2.dylib"
      "libXfixes.3.dylib"
      "libxcb.1.dylib"
      "libXau.6.dylib"
      "libXdmcp.6.dylib"
    )

    # Map a bare name to an actual source path:
    resolve_x11_src() {
        local name="$1"
        # 1) vendored copy?
        if [ -f "$X11_VENDOR_DIR/$name" ]; then
            echo "$X11_VENDOR_DIR/$name"
            return 0
        fi
        # 2) Homebrew "opt" locations (typical)
        case "$name" in
            libX11.6.dylib)      echo "$BREW_PREFIX/opt/libx11/lib/$name"; return 0;;
            libXext.6.dylib)     echo "$BREW_PREFIX/opt/libxext/lib/$name"; return 0;;
            libXinerama.1.dylib) echo "$BREW_PREFIX/opt/libxinerama/lib/$name"; return 0;;
            libXcursor.1.dylib)  echo "$BREW_PREFIX/opt/libxcursor/lib/$name"; return 0;;
            libXv.1.dylib)       echo "$BREW_PREFIX/opt/libxv/lib/$name"; return 0;;
            libXi.6.dylib)       echo "$BREW_PREFIX/opt/libxi/lib/$name"; return 0;;
            libXrender.1.dylib)  echo "$BREW_PREFIX/opt/libxrender/lib/$name"; return 0;;
            libXrandr.2.dylib)   echo "$BREW_PREFIX/opt/libxrandr/lib/$name"; return 0;;
            libXfixes.3.dylib)   echo "$BREW_PREFIX/opt/libxfixes/lib/$name"; return 0;;
            libxcb.1.dylib)      echo "$BREW_PREFIX/opt/libxcb/lib/$name"; return 0;;
            libXau.6.dylib)      echo "$BREW_PREFIX/opt/libxau/lib/$name"; return 0;;
            libXdmcp.6.dylib)    echo "$BREW_PREFIX/opt/libxdmcp/lib/$name"; return 0;;
        esac
        echo ""  # unknown
    }

    # Helper to change a reference if present
    chg_ref() {
        local from="$1" to="$2" file="$3"
        if otool -L "$file" | awk '{print $1}' | grep -Fq "$from"; then
            install_name_tool -change "$from" "$to" "$file"
        fi
    }

    # Recursively copy any Homebrew-provided dep and rewrite to @rpath/<name>
    copy_and_patch_lib() {
        local src="$1"
        local base="$(basename "$src")"
        local dst="$X11_DIR/$base"

        # Skip if already present (acts like a visited-set)
        if [ -f "$dst" ]; then
            return 0
        fi

        if [ ! -f "$src" ]; then
            log "WARN: missing expected lib: $src"
            return 0
        fi

        cp -p "$src" "$dst"
        chmod u+w "$dst"
        install_name_tool -id "@rpath/$base" "$dst"

        # Walk deps; copy any from Homebrew (opt|Cellar), then rewrite to @rpath
        # Note: first line of otool -L is the file itself; skip it.
        otool -L "$dst" | awk 'NR>1{print $1}' | while read -r dep; do
            # skip blank lines
            [ -z "$dep" ] && continue
            # ignore self and system libs
            case "$dep" in
                "$src") continue ;;
                /usr/lib/*) continue ;;
                /System/*) continue ;;
            esac
            local depbase="$(basename "$dep")"
            # Prefer vendored copy if present, else accept Homebrew path we discovered
            local dep_src="$dep"
            if [ -f "$X11_VENDOR_DIR/$depbase" ]; then
                dep_src="$X11_VENDOR_DIR/$depbase"
            fi
            copy_and_patch_lib "$dep_src"
            chg_ref "$dep" "@rpath/$depbase" "$dst"
        done
    }

    log "Bundling X11 dylibs (with recursive Homebrew deps)..."
    for name in "${REQUIRED_X11[@]}"; do
        src_path="$(resolve_x11_src "$name")"
        if [ -n "$src_path" ]; then
            copy_and_patch_lib "$src_path"
        else
            log "WARN: Unresolved X11 lib name: $name"
        fi
    done

    # Ensure files are writable; many shipped as 444
    find "$APP_FRAMEWORKS" -type f -name "*.dylib" -exec chmod u+w {} +
    chmod u+w "$APP_MACOS/xfreerdp"

    # Make xfreerdp find both freerdp and x11
    install_name_tool -add_rpath "@executable_path/../Frameworks/x11" "$FREERDP_BIN" 2>/dev/null || true

    # Repoint any remaining Homebrew X11 refs in xfreerdp -> @rpath/<name>
    otool -L "$FREERDP_BIN" | awk 'NR>1{print $1}' | while read -r dep; do
        [ -z "$dep" ] && continue
        case "$dep" in
            "$BREW_PREFIX"/*/lib/*.dylib|"$BREW_PREFIX"/opt/*/lib/*.dylib)
            base="$(basename "$dep")"
            chg_ref "$dep" "@rpath/$base" "$FREERDP_BIN"
            ;;
        esac
    done

    # Clear quarantine early (if present), do this before codesign to avoid EPERM
    xattr -dr com.apple.quarantine "dist/$NAME.app" || true

    # Rewrite any remaining X11 references in xfreerdp from Homebrew paths -> @rpath/<name>
    otool -L "$FREERDP_BIN" | awk 'NR>1{print $1}' | while read -r dep; do
        [ -z "$dep" ] && continue
        if echo "$dep" | grep -Eq "^$BREW_PREFIX/(opt|Cellar)/"; then
            base="$(basename "$dep")"
            chg_ref "$dep" "@rpath/$base" "$FREERDP_BIN"
        fi
    done

    # Quick verification (optional)
    log "Verifying X11 + rpaths on xfreerdp:"
    otool -L "$FREERDP_BIN" | sed 's/^/  /'
    otool -l "$FREERDP_BIN" | awk '/LC_RPATH/{flag=1;print;next}/cmd /{flag=0}flag' | sed 's/^/  /'

    # Ad-hoc sign libraries and the app so macOS doesn’t kill the process
    log "Ad-hoc codesigning bundled libs and app..."
    find "$APP_FRAMEWORKS" -type f -name "*.dylib" -exec codesign --force --timestamp=none -s - {} \;
    codesign --force --timestamp=none -s - "$FREERDP_BIN"
    codesign --force --deep --timestamp=none -s - "dist/$NAME.app"
    # ---- END: Bundle X11 stack + add rpath + ad-hoc sign ----
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
