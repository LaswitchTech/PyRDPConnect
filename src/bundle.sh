#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <binary-name>" >&2
    exit 1
fi

TARGET_BIN="$1"

# Root of your project (adjust if needed)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OS="linux"
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
    echo "${TARGET_BIN} not found in PATH. Install it first." >&2
    exit 1
fi

echo "Found ${TARGET_BIN} at: $SOURCE_BIN"
echo "Copying to: $DEST_DIR/${TARGET_BIN}"

cp "$SOURCE_BIN" "$DEST_DIR/${TARGET_BIN}"
chmod 755 "$DEST_DIR/${TARGET_BIN}"

echo "Done."
