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

# Check if we're running in GitHub Actions (environment variables are already set)
if [ -n "$GITHUB_ACTIONS" ]; then
    echo "Running in GitHub Actions - using environment variables..."
else
    # Running locally - check for .env file
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
fi

if [ -z "$APPLE_ID" ] || [ -z "$APPLE_APP_SPECIFIC_PASSWORD" ] || [ -z "$APPLE_TEAM_ID" ]; then
    echo "Error: Ensure APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID are set."
    exit 1
fi

if [ -z "$MACOS_SIGNING_CERT_BASE64" ] || [ -z "$MACOS_SIGNING_CERT_PASSWORD" ]; then
    echo "Error: Ensure MACOS_SIGNING_CERT_BASE64 and MACOS_SIGNING_CERT_PASSWORD are set."
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
security import "$CERT_PATH" -k "$KEYCHAIN_PATH" -P "$MACOS_SIGNING_CERT_PASSWORD" -A

# Configure keychain for GitHub Actions
if [ -n "$GITHUB_ACTIONS" ]; then
    echo "Configuring keychain for GitHub Actions..."
    # Add keychain to search list and make it default
    security list-keychains -d user -s "$KEYCHAIN_PATH" $(security list-keychains -d user | sed s/\"//g)
    security default-keychain -s "$KEYCHAIN_PATH"
    # Set key partition list for automated access
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "" "$KEYCHAIN_PATH"
else
    # For local development, just add to search list
    security list-keychains -d user -s "$KEYCHAIN_PATH" $(security list-keychains -d user | sed s/\"//g)
fi

echo "Certificate imported successfully."

echo "--- Section 4: Signing Application Files ---"
APP_SIGNING_IDENTITY="Developer ID Application"
echo "Using signing identity: $APP_SIGNING_IDENTITY"

ENTITLEMENTS_FILE="scripts/mac/entitlements.plist"

# Step 4a: Sign regular files
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

# Step 4b: Handle JAR files with native libraries
echo "Checking for JAR files with native libraries..."
if command -v jar >/dev/null 2>&1; then
    while IFS= read -r jar_file; do
        if [ -f "$jar_file" ]; then
            echo "Processing JAR: $(basename "$jar_file")"

            # Create temporary directory for extraction
            JAR_TEMP_DIR=$(mktemp -d)
            ORIGINAL_DIR=$(pwd)

            # Extract JAR (JAR files are ZIP files)
            cd "$JAR_TEMP_DIR"
            unzip -q "$ORIGINAL_DIR/$jar_file"

            # Find and sign any .dylib files in the extracted content
            JAR_MODIFIED=false
            while IFS= read -r dylib_file; do
                if [ -f "$dylib_file" ]; then
                    echo "  Signing native library in JAR: $dylib_file"
                    codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$dylib_file" --verbose=2
                    JAR_MODIFIED=true
                fi
            done <<<"$(find . -name "*.dylib" -type f)"

            # If we signed anything, repackage the JAR
            if [ "$JAR_MODIFIED" = true ]; then
                echo "  Repackaging JAR: $(basename "$jar_file")"
                zip -qr "$ORIGINAL_DIR/$jar_file" *
            fi

            cd "$ORIGINAL_DIR"
            rm -rf "$JAR_TEMP_DIR"
        fi
    done <<<"$(find "$PROJECT_DIR" -name "*.jar" -type f)"
else
    echo "Note: jar command not available, skipping JAR file processing"
    echo "Warning: Native libraries in JAR files may not be signed"
fi

echo "Application file signing complete."
echo

# --- 5. Create DMG ---

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

# Restore original default keychain if we changed it
if [ -n "$GITHUB_ACTIONS" ]; then
    security default-keychain -s ~/Library/Keychains/login.keychain-db 2>/dev/null || true
fi

security delete-keychain "$KEYCHAIN_PATH"
rm -f "$CERT_PATH"
echo "Cleanup complete."
echo

# --- 8. Final Verification ---
echo "--- Section 8: Final Verification ---"
echo "Verifying stapled ticket..."
xcrun stapler validate "$DMG_PATH"
echo

# --- 9. Summary ---
echo "=== Summary ==="
echo "Process finished successfully!"
echo "Final distributable disk image is at: $DMG_PATH"
echo "  - To install, open the DMG and drag the '$VERSION_FOLDER' folder to:"
echo "    • Any writable folder in your home directory"
echo "  - Note: Do NOT place in /Applications - the app needs write access to its folder."
echo
