#!/usr/bin/env bash
#
# macOS Sign and Notarize Script (using Environment Variables)
#
# This script signs and notarizes a pre-built macOS application using
# certificates provided via environment variables.
#
# Prerequisites:
#   1. Build the app first: python scripts/export/export.py
#   2. Set up .env file with signing certificates and Apple notarization credentials.
#      Required variables: MACOS_SIGNING_CERT_BASE64, MACOS_SIGNING_CERT_PASSWORD,
#      APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
#
# Options:
#   --build-only: Skip notarization steps (for testing)
#

set -e

# Parse command line arguments
BUILD_ONLY=false
SIGN_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            ;;
        --sign-only)
            SIGN_ONLY=true
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--build-only|--sign-only]"
            exit 1
            ;;
    esac
    shift
done

if [ "$BUILD_ONLY" = true ]; then
    echo "=== macOS Build Script (Build Only Mode - Sign but Skip Notarization) ==="
elif [ "$SIGN_ONLY" = true ]; then
    echo "=== macOS Sign Script (Sign Only Mode) ==="
else
    echo "=== macOS Sign & Notarize Script (using Environment Variables) ==="
fi
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
        if [ "$BUILD_ONLY" = false ]; then
            echo "                   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID"
        fi
        exit 1
    fi

    echo "Sourcing secrets from .env file..."
    set -o allexport
    source .env
    set +o allexport
fi

# Check notarization credentials (not needed in build-only mode)
if [ "$BUILD_ONLY" = false ]; then
    if [ -z "$APPLE_ID" ] || [ -z "$APPLE_APP_SPECIFIC_PASSWORD" ] || [ -z "$APPLE_TEAM_ID" ]; then
        echo "Error: Ensure APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID are set."
        exit 1
    fi
fi

# Check signing credentials (needed for both modes)
if [ -z "$MACOS_SIGNING_CERT_BASE64" ] || [ -z "$MACOS_SIGNING_CERT_PASSWORD" ]; then
    echo "Error: Ensure MACOS_SIGNING_CERT_BASE64 and MACOS_SIGNING_CERT_PASSWORD are set."
    exit 1
fi
echo "Environment variables loaded successfully."
echo

# --- 2. Check for Pre-built Application ---

echo "--- Section 2: Checking for Pre-built Application ---"
echo "Note: This script requires you to build the application first using:"
echo "  python scripts/export/export.py"
echo

# Find the project directory (not the .app bundle)
PROJECT_DIR=$(find "dist" -type d -name "sharly-chess-*" ! -name "*.app" -print -quit 2>/dev/null || true)
if [ -z "$PROJECT_DIR" ]; then
    echo "Error: No PyInstaller project directory found in dist/"
    exit 1
fi
echo "Found pre-built project directory: $PROJECT_DIR"
echo

# --- 3. Configure SharlyChess.app Bundle ---

echo "--- Section 3: Configuring PyInstaller-generated app bundle ---"

# Extract version from the project directory name
VERSION_FOLDER=$(basename "$PROJECT_DIR")
VERSION=$(echo "$VERSION_FOLDER" | sed 's/sharly-chess-//')
EXECUTABLE_NAME="sharly-chess-${VERSION}"

# PyInstaller creates the app bundle at dist/ root with --windowed flag
PYINSTALLER_APP_BUNDLE=$(find "dist" -maxdepth 1 -name "*.app" -type d -print -quit 2>/dev/null || true)
APP_BUNDLE="$PROJECT_DIR/SharlyChess.app"

if [ -z "$PYINSTALLER_APP_BUNDLE" ]; then
    # Check if SharlyChess.app already exists in project directory
    if [ -d "$APP_BUNDLE" ]; then
        echo "Found existing SharlyChess.app bundle in project directory: $APP_BUNDLE"
    else
        echo "Error: No .app bundle found. PyInstaller may not have created it properly."
        echo "Expected either a .app in dist/ or SharlyChess.app in $PROJECT_DIR"
        exit 1
    fi
else
    echo "Found PyInstaller-generated app bundle: $PYINSTALLER_APP_BUNDLE"
    # Move and rename the app bundle to the project directory as SharlyChess.app
    echo "Moving app bundle to project directory and renaming to SharlyChess.app..."
    mv "$PYINSTALLER_APP_BUNDLE" "$APP_BUNDLE"
fi

# Copy the icon
echo "Adding application icon..."
if [ -f "src/web/static/images/sharly-chess.icns" ]; then
    # Copy the existing ICNS file directly
    cp "src/web/static/images/sharly-chess.icns" "$APP_BUNDLE/Contents/Resources/icon.icns"
    echo "Icon added successfully."
else
    echo "Warning: Icon file not found at src/web/static/images/sharly-chess.icns"
fi

# Update Info.plist to reference our custom icon
if [ -f "$APP_BUNDLE/Contents/Info.plist" ]; then
    # PyInstaller already set an icon file, replace it with our custom one
    plutil -replace CFBundleIconFile -string "icon" "$APP_BUNDLE/Contents/Info.plist"
    # Update the display name and bundle name
    plutil -replace CFBundleDisplayName -string "Sharly Chess" "$APP_BUNDLE/Contents/Info.plist"
    plutil -replace CFBundleName -string "SharlyChess" "$APP_BUNDLE/Contents/Info.plist"
    # Disable App Nap
    plutil -replace NSAppSleepDisabled -bool YES "$APP_BUNDLE/Contents/Info.plist"
    # Set the version so Sparkle can compare the running app against the appcast.
    plutil -replace CFBundleVersion -string "$VERSION" "$APP_BUNDLE/Contents/Info.plist"
    plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP_BUNDLE/Contents/Info.plist"
    echo "Updated Info.plist with custom icon, names and version"
else
    echo "Warning: Info.plist not found in app bundle"
fi

echo "Created SharlyChess.app bundle at: $APP_BUNDLE"
echo

# --- 4. Setup Temporary Keychain and Sign Application Files ---

echo "--- Section 4: Setting up temporary keychain and signing certificates ---"

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

echo "--- Section 5: Signing Application Files ---"
APP_SIGNING_IDENTITY="Developer ID Application"
echo "Using signing identity: $APP_SIGNING_IDENTITY"

ENTITLEMENTS_FILE="scripts/export/macos/entitlements.plist"

# Step 4: Sign files in proper order (inside-out)
echo "Signing all Mach-O files and dylibs inside the app bundle..."

# First, sign all dylibs and .so files (deepest dependencies first)
find "$APP_BUNDLE" -type f \( -name "*.dylib" -o -name "*.so" \) | while read -r file; do
    echo "Signing: $(basename "$file")"
    codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$file" --verbose=2
done

# Then sign executables (but not the main app bundle yet)
find "$APP_BUNDLE" -type f -perm +111 ! -name "*.app" | while read -r file; do
    # Skip the main executable for now, and only sign if it's a Mach-O binary
    if file "$file" | grep -q "Mach-O"; then
        echo "Signing executable: $(basename "$file")"
        if [[ "$(basename "$file")" == "sharly-chess-"* ]]; then
            # Sign main executable with entitlements
            codesign --force --timestamp --options=runtime --entitlements "$ENTITLEMENTS_FILE" --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$file" --verbose=2
        else
            # Sign other executables without entitlements
            codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$file" --verbose=2
        fi
    fi
done

# --- Embed and sign Sparkle.framework (macOS auto-update) ---
# Vendored by scripts/export/macos/fetch_sparkle.sh into vendor/sparkle/.
# Done after the generic find loops (so they don't touch Sparkle) and before
# the outer app is signed (so the seal covers the embedded framework).
SPARKLE_FRAMEWORK_SRC="vendor/sparkle/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK_SRC" ]; then
    echo "Embedding Sparkle.framework..."
    FRAMEWORKS_DIR="$APP_BUNDLE/Contents/Frameworks"
    mkdir -p "$FRAMEWORKS_DIR"
    rm -rf "$FRAMEWORKS_DIR/Sparkle.framework"
    ditto "$SPARKLE_FRAMEWORK_SRC" "$FRAMEWORKS_DIR/Sparkle.framework"
    SPARKLE_FW="$FRAMEWORKS_DIR/Sparkle.framework"
    SPARKLE_V="$SPARKLE_FW/Versions/Current"

    # Configure Sparkle in Info.plist. No SUFeedURL: the app sets the feed at
    # runtime (the per-release appcast chosen by our own version detection).
    # SUEnableAutomaticChecks=NO so only our code ever triggers an update.
    plutil -replace SUEnableAutomaticChecks -bool NO "$APP_BUNDLE/Contents/Info.plist"
    # Local-test only: allow Sparkle to fetch the appcast/zip over http://localhost.
    # Never enable for a release build.
    if [ "${SPARKLE_LOCAL_TEST:-0}" = "1" ]; then
        plutil -replace NSAppTransportSecurity -xml \
            '<dict><key>NSAllowsLocalNetworking</key><true/></dict>' \
            "$APP_BUNDLE/Contents/Info.plist"
        echo "ATS: local networking allowed (SPARKLE_LOCAL_TEST=1)."
    fi
    if [ -n "$SPARKLE_ED_PUBLIC_KEY" ]; then
        plutil -replace SUPublicEDKey -string "$SPARKLE_ED_PUBLIC_KEY" "$APP_BUNDLE/Contents/Info.plist"
        echo "Set SUPublicEDKey in Info.plist."
    else
        echo "Warning: SPARKLE_ED_PUBLIC_KEY not set — Sparkle cannot verify"
        echo "         updates at runtime (fine for build/sign testing only)."
    fi

    # Re-sign Sparkle inside-out with our identity (hardened runtime), so the
    # whole bundle notarizes under one team. Order matters: XPC services, then
    # Updater.app, then Autoupdate, then the framework bundle itself.
    sparkle_sign() {
        codesign --force --timestamp --options=runtime \
            --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$1" --verbose=2
    }
    for xpc in "$SPARKLE_V/XPCServices/"*.xpc; do
        if [ -e "$xpc" ]; then
            echo "Signing Sparkle XPC: $(basename "$xpc")"
            sparkle_sign "$xpc"
        fi
    done
    if [ -d "$SPARKLE_V/Updater.app" ]; then
        echo "Signing Sparkle Updater.app"
        sparkle_sign "$SPARKLE_V/Updater.app"
    fi
    if [ -e "$SPARKLE_V/Autoupdate" ]; then
        echo "Signing Sparkle Autoupdate"
        sparkle_sign "$SPARKLE_V/Autoupdate"
    fi
    echo "Signing Sparkle.framework"
    sparkle_sign "$SPARKLE_FW"
    echo "Sparkle embedded and signed."
else
    echo "Sparkle.framework not vendored (run scripts/export/macos/fetch_sparkle.sh)"
    echo "  — building without the in-app auto-update framework."
fi

# Finally, sign the app bundle itself
echo "Signing the main app bundle: $APP_BUNDLE"
codesign --force --timestamp --options=runtime --entitlements "$ENTITLEMENTS_FILE" --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$APP_BUNDLE" --verbose=2

echo "Application file signing complete."

# --- 6. Create DMG ---

echo "--- Section 6: Creating DMG Disk Image ---"

VERSION_FOLDER=$(basename "$PROJECT_DIR")
VERSION=$(echo "$VERSION_FOLDER" | sed 's/sharly-chess-//')
DMG_NAME="sharly-chess-${VERSION}-macos.dmg"
DMG_PATH="dist/$DMG_NAME"
STAGING_DIR=$(mktemp -d)
VOLUME_NAME="Sharly Chess ${VERSION}"

echo "Staging application content..."
# Flattened layout: SharlyChess.app and the licence/support files sit at the
# DMG top level (no versioned wrapper folder). The app is self-contained and
# self-updates in place via Sparkle; user data lives under
# ~/Library/Application Support, so nothing needs to ship beside the app.
rsync -a "$APP_BUNDLE" "$STAGING_DIR/"

# Copy licence/support files alongside the app (skip build internals + the raw executable).
for item in "$PROJECT_DIR"/*; do
    item_name=$(basename "$item")
    if [[ "$item_name" != "_internal" && "$item_name" != "tools" && "$item_name" != "$EXECUTABLE_NAME" && "$item_name" != "SharlyChess.app" ]]; then
        rsync -a "$item" "$STAGING_DIR/"
    fi
done

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


# --- 7. Sign and Notarize .dmg ---
if [ "$BUILD_ONLY" = true ]; then
    echo "--- Section 7: Signing DMG (Build-Only Mode) ---"
    echo "Build-only mode: Skipping DMG signing and notarization."
else
    echo "--- Section 7: Signing and Notarizing the DMG ---"

    echo "Signing the DMG..."
    codesign --force --timestamp --options=runtime --sign "$APP_SIGNING_IDENTITY" --keychain "$KEYCHAIN_PATH" "$DMG_PATH" --verbose=2

    echo "Notarizing the DMG... (this may take a while)"
    NOTARY_RESULT=$(xcrun notarytool submit "$DMG_PATH" \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait 2>&1)

    echo "$NOTARY_RESULT"

    if echo "$NOTARY_RESULT" | grep -q "status: Accepted"; then
        echo "Notarization successful. Stapling ticket..."
        xcrun stapler staple "$DMG_PATH"
        echo "Stapling complete."
    else
        echo "Error: Notarization failed!"
        # Extract submission ID to get detailed logs
        SUBMISSION_ID=$(echo "$NOTARY_RESULT" | grep "id:" | head -1 | awk '{print $2}')
        if [ -n "$SUBMISSION_ID" ]; then
            echo "Getting detailed notarization logs..."
            xcrun notarytool log "$SUBMISSION_ID" \
                --apple-id "$APPLE_ID" \
                --password "$APPLE_APP_SPECIFIC_PASSWORD" \
                --team-id "$APPLE_TEAM_ID"
        fi
        exit 1
    fi
fi
echo


# --- 8. Clean up temporary keychain ---
echo "--- Section 8: Cleaning up temporary keychain ---"
echo "Removing temporary keychain and certificate..."

# Restore original default keychain if we changed it
if [ -n "$GITHUB_ACTIONS" ]; then
    security default-keychain -s ~/Library/Keychains/login.keychain-db 2>/dev/null || true
fi

security delete-keychain "$KEYCHAIN_PATH"
rm -f "$CERT_PATH"
echo "Cleanup complete."
echo

# --- 9. Final Verification ---
if [ "$BUILD_ONLY" = false ]; then
    echo "--- Section 9: Final Verification ---"
    echo "Verifying stapled ticket..."
    xcrun stapler validate "$DMG_PATH"
    echo
fi

# --- 10. Summary ---
echo "=== Summary ==="
if [ "$BUILD_ONLY" = true ]; then
    echo "Build process finished successfully (signed but not notarized)!"
else
    echo "Process finished successfully!"
fi
echo "Final distributable disk image is at: $DMG_PATH"
echo "  - Top level: SharlyChess.app + licence/support files (no versioned folder)"
echo "    - SharlyChess.app (properly signed app bundle with all dependencies)"
echo "  - The SharlyChess.app will launch the application in GUI mode"
if [ "$BUILD_ONLY" = true ]; then
    echo "  - Note: This app is signed but NOT notarized (build-only mode)"
else
    echo "  - This app is fully signed and notarized for distribution"
fi
echo "  - To install, extract the DMG contents to any writable folder in your home directory"
echo "  - Note: Do NOT place in /Applications - the app needs write access to its folder."
echo
