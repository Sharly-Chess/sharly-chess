#!/usr/bin/env bash
#
# Fetch a pinned Sparkle 2 release and vendor it under vendor/sparkle/.
#
# Used by:
#   * the macOS build (build_and_notarize.sh embeds Sparkle.framework)
#   * appcast signing (bin/sign_update, bin/generate_appcast)
#
# See docs/technical-appendices/mac/sparkle-auto-update.md for the full guide.
#
# Output layout (vendor/ is gitignored; kept out of build/ so the export,
# which wipes build/, doesn't delete it):
#   vendor/sparkle/Sparkle.framework
#   vendor/sparkle/bin/{sign_update,generate_keys,generate_appcast,BinaryDelta}
#
# Idempotent: re-running is a no-op unless SPARKLE_FORCE=1.
#
# Usage:
#   scripts/export/macos/fetch_sparkle.sh
#   SPARKLE_VERSION=2.6.4 scripts/export/macos/fetch_sparkle.sh

set -euo pipefail

# Pin the Sparkle version here. Check the latest at
# https://github.com/sparkle-project/Sparkle/releases and bump when needed.
SPARKLE_VERSION="${SPARKLE_VERSION:-2.6.4}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEST_DIR="${SPARKLE_DEST:-$REPO_ROOT/vendor/sparkle}"
FRAMEWORK="$DEST_DIR/Sparkle.framework"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "fetch_sparkle: Sparkle is macOS-only; nothing to do on $(uname -s)." >&2
    exit 0
fi

if [[ -d "$FRAMEWORK" && "${SPARKLE_FORCE:-0}" != "1" ]]; then
    echo "Sparkle $SPARKLE_VERSION already vendored at $DEST_DIR"
    echo "SPARKLE_FRAMEWORK=$FRAMEWORK"
    exit 0
fi

url="https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/Sparkle-${SPARKLE_VERSION}.tar.xz"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "Downloading Sparkle $SPARKLE_VERSION ..."
curl -fSL "$url" -o "$tmp/sparkle.tar.xz"
tar -xJf "$tmp/sparkle.tar.xz" -C "$tmp"

if [[ ! -d "$tmp/Sparkle.framework" ]]; then
    echo "fetch_sparkle: Sparkle.framework not found in the archive." >&2
    exit 1
fi

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
# Preserve symlinks/signatures inside the framework with ditto.
ditto "$tmp/Sparkle.framework" "$FRAMEWORK"
if [[ -d "$tmp/bin" ]]; then
    ditto "$tmp/bin" "$DEST_DIR/bin"
fi

echo "Sparkle $SPARKLE_VERSION vendored at $DEST_DIR"
echo "SPARKLE_FRAMEWORK=$FRAMEWORK"
