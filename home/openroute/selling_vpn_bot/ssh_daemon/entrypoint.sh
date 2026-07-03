#!/bin/bash
set -e

# Dynamically set root password if provided via environment variable
if [ -n "$ROOT_PASSWORD" ]; then
    echo "root:$ROOT_PASSWORD" | chpasswd
    echo "Root password updated."
else
    echo "WARNING: ROOT_PASSWORD env variable not set. Defaulting to standard SSH keys or existing password."
fi

# Ensure host keys are generated if they do not exist
ssh-keygen -A

# Copy and configure traffic tracking scripts from mounted /app/scripts directory
if [ -d "/app/scripts" ]; then
    echo "Deploying traffic tracking scripts..."
    cp /app/scripts/setup_user_traffic.sh /usr/local/bin/setup_user_traffic.sh
    cp /app/scripts/read_user_traffic.sh /usr/local/bin/read_user_traffic.sh
    chmod +x /usr/local/bin/setup_user_traffic.sh
    chmod +x /usr/local/bin/read_user_traffic.sh
    echo "Scripts deployed successfully."
else
    echo "WARNING: /app/scripts not mounted or not found!"
fi

# Run SSH daemon in the foreground
echo "Starting SSH daemon..."
exec /usr/sbin/sshd -D
