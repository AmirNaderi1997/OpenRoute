#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== 1. Checking Nginx Listen Directives in Sites-Available ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "grep -rn 'listen' /etc/nginx/sites-available/"

echo -e "\n=== 2. Checking Nginx Listen Directives in Nginx.conf ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "grep -rn 'listen' /etc/nginx/nginx.conf"
