#!/bin/bash
#
# macOS Sign and Notarize Script (using System Keychain)
#
# This script signs and notarizes a pre-built macOS application using
# the Developer ID certificates already present in your system's login keychain.
#
# Prerequisites:
#   1. Build the app first: python scripts/export/export.py --preserve-build
#   2. Have valid "Developer ID Application" and "Developer ID Installer" certificates
#      in your login keychain.
#   3. Set up .env file with Apple notarization credentials (APPLE_ID, etc.).
#

set -e

echo "=== macOS Sign & Notarize Script (using System Keychain) ==="
echo

# --- 1. Environment and Prerequisite Checks ---

echo "--- Section 1: Environment and Prerequisite Checks ---"

if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please create one with your Apple notarization secrets."
    echo "It should contain: APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID"
    exit 1
fi

echo "Sourcing secrets from .env file..."
set -o allexport
source .env
set +o allexport

if [ -z "$APPLE_ID" ] || [ -z "$APPLE_APP_SPECIFIC_PASSWORD" ] || [ -z "$APPLE_TEAM_ID" ]; then
    echo "Error: Ensure APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID are set in the .env file."
    exit 1
fi
echo "Environment variables loaded successfully."
echo

# --- 2. Check for Pre-built Application ---

echo "--- Section 2: Checking for Pre-built Application ---"
echo "Note: This script requires you to build the application first using:"
echo "  python scripts/export/export.py --preserve-build"
echo

PROJECT_DIR=$(find "dist" -type d -name "sharly-chess-*" -print -quit 2>/dev/null || true)
if [ -z "$PROJECT_DIR" ]; then
    echo "Error: No PyInstaller project directory found in dist/"
    exit 1
fi
echo "Found pre-built project directory: $PROJECT_DIR"
echo

# --- 3. Sign Application Files ---

echo "--- Section 3: Signing Application Files ---"
APP_SIGNING_IDENTITY="Developer ID Application: Arctic Whiteness (MXZ782EHFK)"
echo "Using signing identity: $APP_SIGNING_IDENTITY"

ENTITLEMENTS_FILE="scripts/mac/entitlements.plist"

while IFS= read -r file; do
    if file "$file" | grep -q "Mach-O" || [[ "$file" == *.app* ]]; then
        echo "Signing: $(basename "$file")"
        # Sign the main executable and the launcher app with entitlements
        if [[ "$(basename "$file")" == "sharly-chess-"* ]] || [[ "$file" == *.app* ]]; then
            codesign --force --timestamp --options=runtime --entitlements "$ENTITLEMENTS_FILE" --sign "$APP_SIGNING_IDENTITY" "$file" --verbose=2
        else
            # Sign other files without entitlements
            codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" "$file" --verbose=2
        fi
    fi
done <<<"$(find "$PROJECT_DIR" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -o -name "*.app")"
echo "Application file signing complete."
echo

# --- 4. Create DMG ---
echo
echo "--- Section 4: Creating DMG Disk Image ---"

VERSION_FOLDER=$(basename "$PROJECT_DIR")
VERSION=$(echo "$VERSION_FOLDER" | sed 's/sharly-chess-//')
DMG_NAME="sharly-chess-${VERSION}-macos.dmg"
DMG_PATH="dist/$DMG_NAME"
STAGING_DIR=$(mktemp -d)
VOLUME_NAME="Sharly Chess ${VERSION}"

echo "Staging application content..."
# Create a directory inside staging with the project name
mkdir -p "$STAGING_DIR/$VERSION_FOLDER"
# Copy the application content into it
rsync -a "$PROJECT_DIR/" "$STAGING_DIR/$VERSION_FOLDER/"

# Calculate the size needed for the DMG. du -sk gives size in KB.
SIZE_KB=$(du -sk "$STAGING_DIR" | awk '{print $1}')
SIZE_MB=$((($SIZE_KB / 1024) + 20)) # Add 20MB buffer for filesystem overhead

TEMP_DMG="dist/tmp.$DMG_NAME"
echo "Creating temporary DMG of size ${SIZE_MB}MB..."
hdiutil create -srcfolder "$STAGING_DIR" -volname "$VOLUME_NAME" -fs HFS+ \
    -format UDRW -size ${SIZE_MB}m "$TEMP_DMG"

echo "Compressing and finalizing DMG..."
rm -f "$DMG_PATH" # Remove old final DMG if it exists
hdiutil convert "$TEMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"

echo "Cleaning up temporary files..."
rm "$TEMP_DMG"
rm -rf "$STAGING_DIR"
echo "DMG created successfully at: $DMG_PATH"
echo


# --- 5. Sign and Notarize .dmg ---
echo "--- Section 5: Signing and Notarizing the DMG ---"

echo "Signing the DMG..."
codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" "$DMG_PATH" --verbose=2

echo "Notarizing the DMG... (this may take a while)"
xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_SPECIFIC_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait

echo "Notarization successful. Stapling ticket..."
xcrun stapler staple "$DMG_PATH"
echo "Stapling complete."
echo


# --- 6. Final Verification ---
echo "--- Section 6: Final Verification ---"
echo "Verifying stapled ticket..."
xcrun stapler validate "$DMG_PATH"
echo "Verifying DMG assessment..."
spctl --assess -v --type open "$DMG_PATH"
echo "Verification complete."
echo


# --- 7. Summary ---
echo "=== Summary ==="
echo "✓ Process finished successfully!"
echo "Final distributable disk image is at: $DMG_PATH"
echo "  - To install, open the DMG and drag the '$VERSION_FOLDER' folder to:"
echo "    • Your Desktop (~/Desktop)"
echo "    • Your Documents folder (~/Documents)"
echo "    • Any writable folder in your home directory"
echo "  - Note: Do NOT place in /Applications - the app needs write access to its folder."
echo

