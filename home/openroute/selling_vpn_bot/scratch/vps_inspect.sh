#!/bin/bash
# Diagnostics script to check remote VPS SSL and Nginx state

VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== 1. Checking Nginx sites-enabled symlinks ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "ls -la /etc/nginx/sites-enabled/"

echo -e "\n=== 2. Checking openroute.ir.conf content in Nginx ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "cat /etc/nginx/sites-available/openroute.ir.conf 2>/dev/null || echo 'Not found'"

echo -e "\n=== 3. Checking Certbot Certificates ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "certbot certificates 2>/dev/null || echo 'Certbot failed or not installed'"

echo -e "\n=== 4. Checking LetsEncrypt live directories ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "ls -la /etc/letsencrypt/live/ 2>/dev/null || echo 'No live certs found'"

echo -e "\n=== 5. Checking all loaded Nginx server names ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "nginx -T 2>/dev/null | grep 'server_name' | sort -u"
