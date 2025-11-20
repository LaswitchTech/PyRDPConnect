#!/usr/bin/env bash
set -euo pipefail

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

DEST_DIR="$PROJECT_ROOT/src/bin/openvpn/${OS}/${ARCH}"
mkdir -p "$DEST_DIR"

OPENVPN_BIN="$(command -v openvpn || true)"

if [[ -z "$OPENVPN_BIN" ]]; then
    echo "openvpn not found in PATH. Install it first, e.g.:" >&2
    echo "  sudo apt update && sudo apt install openvpn" >&2
    exit 1
fi

echo "Found openvpn at: $OPENVPN_BIN"
echo "Copying to: $DEST_DIR/openvpn"

cp "$OPENVPN_BIN" "$DEST_DIR/openvpn"
chmod 755 "$DEST_DIR/openvpn"

echo "Done."
