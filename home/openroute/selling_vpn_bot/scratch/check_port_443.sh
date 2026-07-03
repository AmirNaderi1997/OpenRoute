#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== Checking what is listening on port 443 on VPS ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "ss -tulpn | grep :443 || netstat -tulpn | grep :443 || lsof -i :443"
