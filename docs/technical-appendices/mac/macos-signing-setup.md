# macOS App Signing and Notarization Setup

This guide explains how to set up code signing and notarization for the macOS version of your exported application. The signing process ensures your app can run on macOS without security warnings and distributes properly to end users.

## Overview

The GitHub Actions workflow automatically:

1. **Signs** all binaries and libraries in the app bundle with your Apple Developer ID
2. **Notarizes** the signed app with Apple's servers
3. **Staples** the notarization ticket to the app
4. **Uploads** the signed and notarized app as a release artifact

## Prerequisites

You need:
- An active **Apple Developer Program** membership
- A **Developer ID Application** certificate in your keychain
- Access to your Apple ID and the ability to generate app-specific passwords

## Step 1: Verify Your Developer ID Certificate

First, check if you already have a Developer ID Application certificate:

```bash
security find-identity -v -p codesigning
```

You should see output like:
```
1) XXXXXXXXXX "Developer ID Application: Your Name (TEAM_ID)"
```

If you don't have one, you need to:
1. Log into [Apple Developer Portal](https://developer.apple.com/account/resources/certificates/list)
2. Create a new **Developer ID Application** certificate
3. Download and install it by double-clicking the `.cer` file

## Step 2: Get Your Apple Team ID

Find your Team ID using:

```bash
# This shows your Team ID in the certificate
security find-identity -v -p codesigning | grep "Developer ID Application"
```

The Team ID is the 10-character string in parentheses at the end.

Alternatively, you can find it in the [Apple Developer Portal](https://developer.apple.com/account#MembershipDetailsCard) under "Membership Details".

## Step 3: Generate App-Specific Password

1. Go to [Apple ID Account Settings](https://appleid.apple.com/account/manage)
2. Sign in with your Apple ID
3. In the "Security" section, under "App-Specific Passwords", click "Generate Password"
4. Enter a label like "GitHub Actions Notarization"
5. Save the generated password - you'll need it for GitHub secrets

## Step 4: Environment Variables Setup for local testing

Create a `.env` file in your project root with the following content:

```plaintext
# Your Apple Developer credentials
APPLE_ID=your_apple_id@example.com
APPLE_APP_SPECIFIC_PASSWORD=abcd-efgh-ijkl-mnop
APPLE_TEAM_ID=ABCDEFGHIJ
```

**Important:**
- Do not commit your `.env` to Git.
- Use the provided `.env.example` file as a template:
  ```bash
  cp .env.example .env
  # Then edit .env with your actual values
  ```

## Step 5: Add Your Certificate to the env file

Run the following command to convert your .p12 certificate to Base64 for secure storage in GitHub and local `.env`:

```bash
./scripts/export/macos/export_cert_to_env.sh
```

You'll be prompted to enter your system password, and to choose a password for the exported certificate.
The Base64 encoded certificate and the password will be added to your `.env` file.

## Step 6: Local Testing

You can now sign and notarize builds locally using the included script:

```bash
# First, build the application
python scripts/export/export.py

# Then run the signing and notarization script
./scripts/export/macos/build_and_notarize.sh
```

The script will:
1. Load credentials from your `.env` file
2. Create a temporary keychain with your certificate
3. Sign all application files
4. Create a DMG disk image
5. Sign and notarize the DMG
6. Staple the notarization ticket
7. Clean up temporary files

The final signed and notarized DMG will be in the `dist/` directory.

## Step 7: Set Up GitHub Repository Secrets

In your GitHub repository, go to **Settings -> Secrets and variables -> Actions** and add these secrets from the .env.

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `MACOS_SIGNING_CERT_BASE64` | Contents of `developer_id_base64.txt` | Base64-encoded .p12 certificate |
| `MACOS_SIGNING_CERT_PASSWORD` | Password you set for the .p12 file | Certificate export password |
| `APPLE_DEVELOPER_USERNAME` | Your Apple ID email address | Apple ID for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password from Step 4 | Notarization authentication |
| `APPLE_TEAM_ID` | Your 10-character Team ID | Apple Developer Team ID |

## Verification

After setting up the secrets, trigger a release build to test the signing:

1. Push a tag or create a release
2. Monitor the GitHub Actions workflow
3. Check the logs for successful signing and notarization
4. Download the signed app and verify it runs without security warnings

## Troubleshooting

### Certificate Issues
```bash
# List all certificates in detail
security find-identity -v -p codesigning

# Check certificate validity dates
security find-certificate -a -c "Developer ID Application" -p | openssl x509 -text -noout
```

### Keychain Issues
```bash
# Unlock login keychain if needed
security unlock-keychain login.keychain
```

### Team ID Issues
```bash
# Get detailed certificate info including Team ID
security find-certificate -a -c "Developer ID Application" -p | openssl x509 -text -noout | grep "Subject:"
```

## Security Notes

- **Keep your secrets secure**: Only repository administrators should have access to these secrets
- **Use app-specific passwords**: Never use your main Apple ID password
- **Certificate expiration**: Developer ID certificates expire after 5 years - monitor expiration dates
- **Team changes**: If you transfer the project to an organization, update the certificates and Team ID

## Personal vs Organization Accounts

This setup works with personal Apple Developer accounts. For open-source projects, using a personal account is common and acceptable. If you later obtain an organization developer account:

1. Create new certificates under the organization account
2. Update all the GitHub secrets with the new values
3. The workflow will continue to work without code changes

## Next Steps

Once signing is set up:
1. Test with a release build
2. Verify the signed app works on different macOS versions
3. Consider setting up automated testing on signed builds
4. Monitor certificate expiration dates

The signing process is fully automated after this initial setup - no manual intervention required for each release.
