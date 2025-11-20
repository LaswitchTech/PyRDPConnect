#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <binary-name>" >&2
    exit 1
fi

TARGET_BIN="$1"

# Root of your project (adjust if needed)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
    armv6l|armv7l)
        ARCH="armhf"
        ;;
    aarch64)
        ARCH="arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH" >&2
        exit 1
        ;;
esac

DEST_DIR="$PROJECT_ROOT/src/bin/${TARGET_BIN}/${OS}/${ARCH}"
mkdir -p "$DEST_DIR"

SOURCE_BIN="$(command -v "${TARGET_BIN}" || true)"

if [[ -z "$SOURCE_BIN" ]]; then
    echo "${TARGET_BIN} not found in PATH. Attempting installation..."

    if [[ "$OS" == "macos" ]]; then
        if ! command -v brew >/dev/null 2>&1; then
            echo "Homebrew is required but not installed." >&2
            exit 1
        fi
        echo "Installing ${TARGET_BIN} using Homebrew..."
        brew install "${TARGET_BIN}" || {
            echo "Failed to install ${TARGET_BIN} via Homebrew." >&2
            exit 1
        }
    elif [[ "$OS" == "linux" ]]; then
        echo "Installing ${TARGET_BIN} using apt-get..."
        sudo apt-get update -y
        sudo apt-get install -y "${TARGET_BIN}" || {
            echo "Failed to install ${TARGET_BIN} via apt-get." >&2
            exit 1
        }
    fi

    SOURCE_BIN="$(command -v "${TARGET_BIN}" || true)"
    if [[ -z "$SOURCE_BIN" ]]; then
        echo "Installation succeeded but ${TARGET_BIN} is still not in PATH." >&2
        exit 1
    fi
fi

echo "Found ${TARGET_BIN} at: $SOURCE_BIN"
echo "Copying to: $DEST_DIR/${TARGET_BIN}"

cp "$SOURCE_BIN" "$DEST_DIR/${TARGET_BIN}"
chmod 755 "$DEST_DIR/${TARGET_BIN}"

echo "Done."
