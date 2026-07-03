#!/bin/bash
set -e

echo "=== 1. Updating package lists ==="
apt-get update

echo "=== 2. Installing basic dependencies, Nginx, Certbot ==="
apt-get install -y curl ca-certificates gnupg nginx certbot python3-certbot-nginx python3-pip python3-virtualenv python3-venv

echo "=== 3. Adding Docker GPG key and repository ==="
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "=== 4. Installing Docker ==="
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== 5. Enabling and starting services ==="
systemctl enable --now docker
systemctl enable --now nginx

echo "=== VPS Setup Script Completed Successfully ==="
docker --version
docker compose version
nginx -v
certbot --version
