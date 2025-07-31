#!/bin/bash
#
# macOS Sign and Notarize Script (using Environment Variables)
#
# This script signs and notarizes a pre-built macOS application using
# certificates provided via environment variables.
#
# Prerequisites:
#   1. Build the app first: python scripts/export/export.py --preserve-build
#   2. Set up .env file with signing certificates and Apple notarization credentials.
#      Required variables: MACOS_SIGNING_CERT_BASE64, MACOS_SIGNING_CERT_PASSWORD,
#      APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
#

set -e

echo "=== macOS Sign & Notarize Script (using Environment Variables) ==="
echo

# --- 1. Environment and Prerequisite Checks ---

echo "--- Section 1: Environment and Prerequisite Checks ---"

if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please create one with your signing and notarization secrets."
    echo "It should contain: MACOS_SIGNING_CERT_BASE64, MACOS_SIGNING_CERT_PASSWORD,"
    echo "                   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID"
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

if [ -z "$MACOS_SIGNING_CERT_BASE64" ] || [ -z "$MACOS_SIGNING_CERT_PASSWORD" ]; then
    echo "Error: Ensure MACOS_SIGNING_CERT_BASE64 and MACOS_SIGNING_CERT_PASSWORD are set in the .env file."
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

# --- 3. Setup Temporary Keychain and Sign Application Files ---

echo "--- Section 3: Setting up temporary keychain and signing certificates ---"

# Create a temporary keychain
if [ -z "$RUNNER_TEMP" ]; then
    RUNNER_TEMP=$(mktemp -d)
fi
KEYCHAIN_PATH=$RUNNER_TEMP/app-signing.keychain-db
echo "Creating temporary keychain at: $KEYCHAIN_PATH"
security create-keychain -p "" "$KEYCHAIN_PATH"
security set-keychain-settings -t 3600 -u "$KEYCHAIN_PATH"
security unlock-keychain -p "" "$KEYCHAIN_PATH"

# Import the signing certificate from environment variable
echo "Importing signing certificate..."
CERT_PATH=$RUNNER_TEMP/certificate.p12
echo -n "$MACOS_SIGNING_CERT_BASE64" | base64 --decode -o "$CERT_PATH"
security import "$CERT_PATH" -k "$KEYCHAIN_PATH" -P "$MACOS_SIGNING_CERT_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple: -s -k "" "$KEYCHAIN_PATH"
echo "Certificate imported successfully."

echo "--- Section 4: Signing Application Files ---"
APP_SIGNING_IDENTITY="Developer ID Application"
echo "Using signing identity: $APP_SIGNING_IDENTITY"

ENTITLEMENTS_FILE="scripts/mac/entitlements.plist"

while IFS= read -r file; do
    if file "$file" | grep -q "Mach-O" || [[ "$file" == *.app* ]]; then
        echo "Signing: $(basename "$file")"
        # Sign the main executable and the launcher app with entitlements
        if [[ "$(basename "$file")" == "sharly-chess-"* ]] || [[ "$file" == *.app* ]]; then
            codesign --force --timestamp --options=runtime --entitlements "$ENTITLEMENTS_FILE" --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$file" --verbose=2
        else
            # Sign other files without entitlements
            codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$file" --verbose=2
        fi
    fi
done <<<"$(find "$PROJECT_DIR" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -o -name "*.app")"
echo "Application file signing complete."
echo

# --- 5. Create DMG ---
echo
echo "--- Section 5: Creating DMG Disk Image ---"

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


# --- 6. Sign and Notarize .dmg ---
echo "--- Section 6: Signing and Notarizing the DMG ---"

echo "Signing the DMG..."
codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$DMG_PATH" --verbose=2

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


# --- 7. Clean up temporary keychain ---
echo "--- Section 7: Cleaning up temporary keychain ---"
echo "Removing temporary keychain and certificate..."
security delete-keychain "$KEYCHAIN_PATH"
rm -f "$CERT_PATH"
echo "Cleanup complete."
echo

# --- 8. Final Verification ---
echo "--- Section 8: Final Verification ---"
echo "Verifying stapled ticket..."
xcrun stapler validate "$DMG_PATH"
echo "Verifying DMG assessment..."
spctl --assess -v --type open "$DMG_PATH"
echo "Verification complete."
echo


# --- 9. Summary ---
echo "=== Summary ==="
echo "✓ Process finished successfully!"
echo "Final distributable disk image is at: $DMG_PATH"
echo "  - To install, open the DMG and drag the '$VERSION_FOLDER' folder to:"
echo "    • Your Desktop (~/Desktop)"
echo "    • Your Documents folder (~/Documents)"
echo "    • Any writable folder in your home directory"
echo "  - Note: Do NOT place in /Applications - the app needs write access to its folder."
echo

