#!/bin/bash

set -e  # Exit on any error

SPECIFIC_EXPORT="/tmp/DeveloperID_specific_export.p12"
BASE64_FILE="/tmp/DeveloperID_specific_base64.txt"
ENV_FILE=".env"
ENV_VAR_NAME="MACOS_SIGNING_CERT_BASE64"
ENV_PASSWORD_VAR_NAME="MACOS_SIGNING_CERT_PASSWORD"

# Step 1: Find available Developer ID Application identities
echo "Searching for Developer ID Application signing identities..."
IDENTITIES_OUTPUT=$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application")

if [ -z "$IDENTITIES_OUTPUT" ]; then
    echo "✗ No Developer ID Application identities found"
    echo "Please ensure you have a valid Developer ID Application certificate installed"
    exit 1
fi

# Count available identities
IDENTITY_COUNT=$(echo "$IDENTITIES_OUTPUT" | wc -l | xargs)
echo "Found $IDENTITY_COUNT Developer ID Application identity(ies):"
echo "$IDENTITIES_OUTPUT"
echo

# If multiple identities, let user choose
if [ "$IDENTITY_COUNT" -gt 1 ]; then
    echo "Multiple identities found. Please select one:"
    echo "$IDENTITIES_OUTPUT" | nl -w2 -s') '
    echo -n "Enter your choice (1-$IDENTITY_COUNT): "
    read -r CHOICE

    if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "$IDENTITY_COUNT" ]; then
        echo "✗ Invalid choice"
        exit 1
    fi

    SELECTED_IDENTITY=$(echo "$IDENTITIES_OUTPUT" | sed -n "${CHOICE}p")
else
    SELECTED_IDENTITY="$IDENTITIES_OUTPUT"
fi

# Extract identity hash and certificate name
IDENTITY_HASH=$(echo "$SELECTED_IDENTITY" | awk '{print $2}')
CERT_NAME=$(echo "$SELECTED_IDENTITY" | sed 's/.*) "//' | sed 's/"$//')

echo "Selected identity:"
echo "  Hash: $IDENTITY_HASH"
echo "  Name: $CERT_NAME"
echo

# Step 2: Set export password
echo "Enter password to protect the exported certificate:"
read -s EXPORT_PASSWORD

# Step 3: Export the identity using the hash to ensure we get both certificate and private key
echo "Attempting to export identity with hash: $IDENTITY_HASH"

# Try to export from all keychains using the identity hash
if security export -t identities -f pkcs12 -P "$EXPORT_PASSWORD" -o "$SPECIFIC_EXPORT" "$IDENTITY_HASH"; then
    echo "✓ Identity exported successfully"
else
    echo "✗ Failed to export identity"
    exit 1
fi

# Step 4: Verify that the PKCS#12 contains a private key
if openssl pkcs12 -in "$SPECIFIC_EXPORT" -nodes -nocerts -passin pass:"$EXPORT_PASSWORD" | grep -q "PRIVATE KEY"; then
    echo "✓ Private key found in PKCS#12 file"
else
    echo "✗ No private key found in the PKCS#12 file"
    rm -f "$SPECIFIC_EXPORT"
    exit 1
fi

# Step 5: Convert to base64
base64 -i "$SPECIFIC_EXPORT" -o "$BASE64_FILE"
BASE64_CONTENT=$(cat "$BASE64_FILE")

# Step 6: Backup and update .env
echo "${ENV_VAR_NAME}=${BASE64_CONTENT}" >> "$ENV_FILE"
echo "${ENV_PASSWORD_VAR_NAME}=${EXPORT_PASSWORD}" >> "$ENV_FILE"

# Step 7: Display the base64 length
echo "Exported certificate length: ${#BASE64_CONTENT} characters"

# Step 8: Instructions
echo "Certificate and password added to .env"
echo "Make sure .env is in your .gitignore file"

echo "Cleaning up..."
rm -f "$SPECIFIC_EXPORT" "$BASE64_FILE"
