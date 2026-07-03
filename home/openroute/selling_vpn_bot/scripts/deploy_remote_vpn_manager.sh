#!/bin/bash
set -euo pipefail

REMOTE_IP="212.74.39.224"
REMOTE_PORT="443"
REMOTE_USER="root"
REMOTE_PASS="1272510662"
REMOTE_DIR="/opt/openroute"

echo "Deploying remote SSH VPN manager to ${REMOTE_IP}:${REMOTE_PORT}"

sshpass -p "$REMOTE_PASS" ssh -p "$REMOTE_PORT" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "$REMOTE_USER@$REMOTE_IP" \
  "mkdir -p $REMOTE_DIR && apt-get update && apt-get install -y python3"

sshpass -p "$REMOTE_PASS" scp -P "$REMOTE_PORT" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "/Users/amirhossein/Documents/selling_vpn_bot/scripts/remote_ssh_vpn_manager.py" \
  "$REMOTE_USER@$REMOTE_IP:$REMOTE_DIR/remote_ssh_vpn_manager.py"

sshpass -p "$REMOTE_PASS" ssh -p "$REMOTE_PORT" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "$REMOTE_USER@$REMOTE_IP" \
  "chmod 700 $REMOTE_DIR/remote_ssh_vpn_manager.py && python3 $REMOTE_DIR/remote_ssh_vpn_manager.py exists --username root >/dev/null"

echo "Remote manager deployed."
