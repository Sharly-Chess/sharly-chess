# macOS Auto-Updates with Sparkle

This guide explains how the macOS build updates itself using
[Sparkle](https://sparkle-project.org/), how to set up the signing keys, and
how to test the whole flow locally without publishing a release.

## Overview

On macOS the app updates itself in place with Sparkle. Responsibilities are
split deliberately:

- **Detection is ours.** `src/common/version_updater.py` queries the GitHub
  releases API to decide whether a newer version exists, which version, and
  whether to include beta channels.
- **Installation is Sparkle's.** Sparkle downloads the new build, verifies its
  EdDSA signature against the public key embedded in the app, confirms the new
  build's code signature matches the running app (same Developer ID), replaces
  the `.app` in place and relaunches.

Sparkle's own scheduled checks are disabled (`SUEnableAutomaticChecks = NO`) and
there is no static `SUFeedURL`. Instead, when the user installs an update, the
app points Sparkle at *that release's* appcast at runtime, via the
`feedURLStringForUpdater:` delegate in `src/common/sparkle_updater.py`. Each
release attaches its own signed `appcast.xml`, so our detection chooses the
feed and Sparkle only verifies and installs.

Windows and Linux are unaffected — they keep their existing update mechanisms.

### Flow at a glance

1. `version_updater` finds a newer release → the app shows an **Install** button.
2. `server_gui_toga._show_update_dialog` calls `sparkle_updater.check_for_update(version)`.
3. `sparkle_updater` loads the embedded `Sparkle.framework`, sets the feed to
   `version_updater.appcast_url(version)` (the release's `appcast.xml` asset),
   and calls Sparkle's `checkForUpdates:`.
4. Sparkle downloads, verifies the EdDSA signature, installs in place, relaunches.

User data is never touched: it lives under
`~/Library/Application Support/com.sharlychess.app/`, separate from the `.app`.

## Prerequisites

- The macOS signing setup from `macos-signing-setup.md` (a Developer ID
  Application certificate and a working `.env`).
- The Sparkle framework and tools, vendored locally (next section).

## Vendoring Sparkle

`scripts/export/macos/fetch_sparkle.sh` downloads a pinned Sparkle release into
`vendor/sparkle/` (which is gitignored). It provides both the framework that
gets embedded in the app and the command-line tools used for signing updates.

```bash
bash scripts/export/macos/fetch_sparkle.sh
```

This creates:

```
vendor/sparkle/Sparkle.framework
vendor/sparkle/bin/{generate_keys,sign_update,generate_appcast,...}
```

The pinned version is the `SPARKLE_VERSION` variable at the top of the script;
bump it to upgrade. `vendor/` is deliberately outside `build/` so that the
export (which wipes `build/`) does not delete it.

## Setting up the signing keys (one time)

Sparkle signs each update with an EdDSA key pair. The public half is embedded in
the app; the private half signs the update archives and must be kept secret.

**1. Generate the key pair.** The private key is stored in your login keychain;
the public key is printed:

```bash
vendor/sparkle/bin/generate_keys
```

It prints something like:

```
<key>SUPublicEDKey</key>
<string>eRPg9U0Fst7zpnA5kqcICr16ZEj+ao7wvTBk6StfHBI=</string>
```

**2. Make the public key available to the build.** Add it to your `.env` (the
build script reads it and writes it into the app's Info.plist as `SUPublicEDKey`):

```plaintext
SPARKLE_ED_PUBLIC_KEY=eRPg9U0Fst7zpnA5kqcICr16ZEj+ao7wvTBk6StfHBI=
```

The public key is not secret; it only needs to match the private key.

**3. Export the private key for CI.** Continuous integration needs the private
key to sign release archives:

```bash
vendor/sparkle/bin/generate_keys -x sparkle_private_key
```

Paste the contents of `sparkle_private_key` into a GitHub Actions secret named
`SPARKLE_ED_PRIVATE_KEY`, then delete the file — never commit it:

```bash
rm sparkle_private_key
```

## How the build embeds Sparkle

When `vendor/sparkle/Sparkle.framework` is present,
`scripts/export/macos/build_and_notarize.sh`:

1. Copies `Sparkle.framework` into `SharlyChess.app/Contents/Frameworks/`.
2. Re-signs it inside-out with your Developer ID and the hardened runtime, in
   the required order: the XPC services, then `Updater.app`, then `Autoupdate`,
   then the framework bundle. (Signing in this order is what lets the whole app
   notarize under one team.)
3. Writes the Sparkle Info.plist keys: `SUPublicEDKey` (from
   `SPARKLE_ED_PUBLIC_KEY`) and `SUEnableAutomaticChecks = NO`.
4. Sets `CFBundleVersion`/`CFBundleShortVersionString` from the build version so
   Sparkle can compare the running app against the appcast.

The DMG is produced with a flat layout — `SharlyChess.app` and the licence files
sit at the top level (there is no versioned wrapper folder). Users drag the app
to any writable location; it then updates itself in place.

If `vendor/sparkle/` is missing, the build still succeeds but without the
auto-update framework, and the app falls back to the legacy updater.

## Publishing a release

Each release must attach a signed `appcast.xml` plus the update archive, so that
`appcast_url(version)` —
`https://github.com/Sharly-Chess/sharly-chess/releases/download/<tag>/appcast.xml` —
resolves. After the app is built, signed and notarized:

```bash
# 1. Zip the app in Sparkle's required format (preserves symlinks + signature).
ditto -c -k --keepParent dist/sharly-chess-<version>/SharlyChess.app SharlyChess.zip

# 2. Generate the signed appcast (reads the version from the zip, signs with the
#    private key in the keychain). The prefix is the release's asset base URL.
vendor/sparkle/bin/generate_appcast \
    --download-url-prefix https://github.com/Sharly-Chess/sharly-chess/releases/download/<tag>/ \
    <folder containing SharlyChess.zip>
```

Attach both `SharlyChess.zip` and the generated `appcast.xml` to the GitHub
release. In CI, the private key comes from the `SPARKLE_ED_PRIVATE_KEY` secret
instead of the keychain.

## Local end-to-end testing (no release)

Sparkle reads the appcast over plain HTTP, so a local web server exercises the
full download → verify → install → relaunch path without any GitHub release.
Two test-only environment overrides make the app reachable offline (both are
harmless in production when unset):

- `SHARLY_CHESS_FAKE_LATEST_VERSION` — pretend a given version is the latest,
  surfacing the Install button without a network call.
- `SHARLY_CHESS_APPCAST_URL` — point Sparkle at a local appcast.

Prerequisites: `.env` contains `SPARKLE_ED_PUBLIC_KEY`, and the matching private
key is in your keychain.

**1. Build the update target (a higher version).** Bump the `version` in
`pyproject.toml` (for example `5.0.0dev1` → `5.0.0dev2`), then:

```bash
python scripts/export/export.py
SPARKLE_LOCAL_TEST=1 ./scripts/export/macos/build_and_notarize.sh --build-only
mkdir -p /tmp/sparkle-feed
ditto -c -k --keepParent \
    dist/sharly-chess-5.0.0.dev2/SharlyChess.app \
    /tmp/sparkle-feed/SharlyChess-5.0.0.dev2.zip
vendor/sparkle/bin/generate_appcast \
    --download-url-prefix http://localhost:8000/ /tmp/sparkle-feed/
```

`SPARKLE_LOCAL_TEST=1` adds an `NSAllowsLocalNetworking` ATS exception so the
`http://localhost` fetch is not blocked. Never set it for a release build.

**2. Build the current app (the lower version).** Revert `pyproject.toml` to the
lower version, then build and copy it to a writable run location so Sparkle can
replace it:

```bash
python scripts/export/export.py
SPARKLE_LOCAL_TEST=1 ./scripts/export/macos/build_and_notarize.sh --build-only
ditto dist/sharly-chess-5.0.0.dev1/SharlyChess.app ~/sparkle-test/SharlyChess.app
```

**3. Serve the feed:**

```bash
cd /tmp/sparkle-feed && python3 -m http.server 8000
```

**4. Run the current app with the overrides and trigger the update:**

```bash
SHARLY_CHESS_FAKE_LATEST_VERSION=5.0.0.dev2 \
SHARLY_CHESS_APPCAST_URL=http://localhost:8000/appcast.xml \
~/sparkle-test/SharlyChess.app/Contents/MacOS/sharly-chess-5.0.0.dev1
```

In the app: **Settings → Search for updates → Install**. Sparkle fetches the
local appcast, downloads the zip, verifies the EdDSA signature, replaces
`~/sparkle-test/SharlyChess.app` and relaunches as the higher version.

## Notes and gotchas

- **Code-signature match.** Sparkle requires the update's signing identity to
  match the running app's. Both builds must be signed with the same Developer ID
  certificate; the build script handles this.
- **Writable location.** The app must live in a user-writable folder (not
  `/Applications`) so Sparkle can replace it without admin rights.
- **Gatekeeper on local tests.** Local test builds are signed but not notarized,
  so the relaunched app may trigger a Gatekeeper prompt. Right-click → Open, or
  clear the quarantine flag:
  `xattr -dr com.apple.quarantine ~/sparkle-test/SharlyChess.app`.
- **Versioning.** Sparkle compares the appcast item against the app's
  `CFBundleVersion`; the build sets it from the build version. Updates only
  register when the appcast advertises a higher version.
- **Bridging.** Sparkle's Objective-C API is driven from Python through
  `rubicon-objc`, the same bridge the app already uses for `NSProcessInfo`.
