#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== 1. Checking Nginx Systemd Status ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "systemctl status nginx.service"

echo -e "\n=== 2. Checking Nginx Error Logs (Journalctl) ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "journalctl -xeu nginx.service -n 50 --no-pager"

echo -e "\n=== 3. Running Nginx Test Manually ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "nginx -t"
