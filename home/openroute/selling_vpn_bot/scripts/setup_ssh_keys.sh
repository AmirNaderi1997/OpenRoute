#!/bin/bash
# setup_ssh_keys.sh
# Generates a secure Ed25519 SSH keypair without a passphrase (if missing)
# and pushes it to the remote VPS using sshpass and ssh-copy-id.

set -e

KEY_PATH="$HOME/.ssh/id_ed25519_vpn_bot"

echo "================================================="
echo "   Automated Secure SSH Key Setup"
echo "================================================="

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <TARGET_VPS_IP> <ROOT_PASSWORD>"
    exit 1
fi

TARGET_IP=$1
ROOT_PASSWORD=$2

# 1. Generate SSH Key Pair
if [ -f "$KEY_PATH" ]; then
    echo "✅ SSH key already exists at $KEY_PATH. Skipping generation."
else
    echo "🛠️  Generating new Ed25519 SSH key at $KEY_PATH..."
    ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -q
    echo "✅ SSH key generated successfully."
fi

# 2. Push to Remote VPS
echo "🚀 Pushing public key to root@$TARGET_IP..."

if ! command -v sshpass &> /dev/null; then
    echo "❌ sshpass is not installed. Please install it (e.g., apt install sshpass or brew install sshpass)."
    exit 1
fi

# Use sshpass to auto-fill the root password and copy the key
sshpass -p "$ROOT_PASSWORD" ssh-copy-id -i "$KEY_PATH.pub" -o StrictHostKeyChecking=no "root@$TARGET_IP"

echo "🎉 Success! The SSH key has been pushed."
echo "⚠️  IMPORTANT: Please update your .env with:"
echo "SSH_PRIVATE_KEY_PATH=$KEY_PATH"
echo "================================================="
