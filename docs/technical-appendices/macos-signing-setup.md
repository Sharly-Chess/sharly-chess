# macOS App Signing and Notarization Setup

This guide explains how to set up code signing and notarization for the macOS version of your exported application using GitHub Actions. The signing process ensures your app can run on macOS without security warnings and distributes properly to end users.

## Overview

The GitHub Actions workflow automatically:
1. **Signs** all binaries and libraries in the app bundle with your Apple Developer ID
2. **Notarizes** the signed app with Apple's servers
3. **Staples** the notarization ticket to the app
4. **Uploads** the signed and notarized app as a release artifact

## Prerequisites

You need:
- An active **Apple Developer Program** membership ($99/year)
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

## Step 2: Export Certificate and Private Key

Use the command line to export your certificate and private key as a .p12 file:

```bash
# Replace "Your Name" with the actual name shown in your certificate
security export -k login.keychain -t identities -f pkcs12 -o ~/Desktop/developer-id-cert.p12 "Developer ID " "Developer ID Application: Your Name (Team ID)"
```

You'll be prompted to:
1. Enter your **login keychain password**
2. Set a **password for the .p12 file** (remember this - you'll need it for GitHub secrets)

## Step 3: Get Your Apple Team ID

Find your Team ID using:

```bash
# This shows your Team ID in the certificate
security find-identity -v -p codesigning | grep "Developer ID Application"
```

The Team ID is the 10-character string in parentheses at the end.

Alternatively, you can find it in the [Apple Developer Portal](https://developer.apple.com/account#MembershipDetailsCard) under "Membership Details".

## Step 4: Generate App-Specific Password

1. Go to [Apple ID Account Settings](https://appleid.apple.com/account/manage)
2. Sign in with your Apple ID
3. In the "Security" section, under "App-Specific Passwords", click "Generate Password"
4. Enter a label like "GitHub Actions Notarization"
5. Save the generated password - you'll need it for GitHub secrets

## Step 5: Encode Certificate for GitHub

Convert your .p12 certificate to Base64 for secure storage in GitHub:

```bash
base64 -i developer_id.p12 -o developer_id_base64.txt
```

## Step 6: Set Up GitHub Repository Secrets

In your GitHub repository, go to **Settings > Secrets and variables > Actions** and add these secrets:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `MACOS_SIGNING_CERT_BASE64` | Contents of `developer_id_base64.txt` | Base64-encoded .p12 certificate |
| `MACOS_SIGNING_CERT_PASSWORD` | Password you set for the .p12 file | Certificate export password |
| `APPLE_DEVELOPER_USERNAME` | Your Apple ID email address | Apple ID for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password from Step 4 | Notarization authentication |
| `APPLE_TEAM_ID` | Your 10-character Team ID | Apple Developer Team ID |

## Step 7: Clean Up Temporary Files

Remove the temporary files from your local machine:

```bash
rm developer_id.p12 developer_id_base64.txt
```

## How the GitHub Workflow Uses These Secrets

The workflow automatically:

1. **Builds the app** using PyInstaller with the `--preserve-build` flag to keep artifacts
2. **Imports the certificate** into a temporary keychain
3. **Signs all components** of the app bundle:
   - Main executable
   - Python extensions and libraries
   - FreeTDS ODBC driver
   - OpenSSL libraries
   - bbpPairings binary
   - The entire app bundle
4. **Creates a ZIP** for notarization
5. **Submits to Apple** for notarization and waits for completion
6. **Staples the ticket** to the app bundle
7. **Recreates ZIP files** with the signed and notarized app
8. **Cleans up** temporary keychains, certificates, and build artifacts

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

## Cost Considerations

- Apple Developer Program: $99/year
- No additional costs for code signing or notarization
- GitHub Actions usage is free for public repositories

## Next Steps

Once signing is set up:
1. Test with a release build
2. Verify the signed app works on different macOS versions
3. Consider setting up automated testing on signed builds
4. Monitor certificate expiration dates

The signing process is fully automated after this initial setup - no manual intervention required for each release.
