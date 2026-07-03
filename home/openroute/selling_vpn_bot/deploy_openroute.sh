#!/bin/bash
set -e

echo "=== 1. Setting up Docker group for openroute user on remote VPS ==="
sshpass -p '1272510662' ssh -o StrictHostKeyChecking=no root@212.74.39.79 "usermod -aG docker openroute || true"

echo "=== 2. Creating archive of the codebase ==="
tar -czf project.tar.gz \
  --exclude=venv \
  --exclude=.git \
  --exclude=webapp/node_modules \
  --exclude=webapp/dist_new \
  --exclude=webapp/dist_new2 \
  --exclude=webapp/dist_new3 \
  .

echo "=== 3. Uploading archive to VPS as openroute user ==="
sshpass -p '1272510662a' scp -o StrictHostKeyChecking=no project.tar.gz openroute@212.74.39.79:/home/openroute/

echo "=== 4. Extracting archive on remote VPS ==="
sshpass -p '1272510662a' ssh -o StrictHostKeyChecking=no openroute@212.74.39.79 "
  mkdir -p /home/openroute/selling_vpn_bot
  tar -xzf /home/openroute/project.tar.gz -C /home/openroute/selling_vpn_bot/
  rm /home/openroute/project.tar.gz
"
rm project.tar.gz

echo "=== 5. Building and starting isolated Docker containers on VPS ==="
sshpass -p '1272510662a' ssh -o StrictHostKeyChecking=no openroute@212.74.39.79 "
  export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH
  cd /home/openroute/selling_vpn_bot
  docker-compose down --remove-orphans || true
  docker-compose build
  docker-compose up -d
"

echo "=== 6. Deploying Nginx configurations ==="
# 1. Create a temporary HTTP-only config file on the VPS
sshpass -p '1272510662' ssh -o StrictHostKeyChecking=no root@212.74.39.79 "
  echo 'server { listen 80; listen [::]:80; server_name openroute.ir; }' > /etc/nginx/sites-available/openroute.ir.conf
  ln -sf /etc/nginx/sites-available/openroute.ir.conf /etc/nginx/sites-enabled/
  nginx -t && systemctl restart nginx
"

# 2. Check and obtain SSL certificate using Nginx plugin
sshpass -p '1272510662' ssh -o StrictHostKeyChecking=no root@212.74.39.79 "
  # Install Certbot Nginx plugin if missing
  if ! dpkg -s python3-certbot-nginx >/dev/null 2>&1; then
    echo 'Installing python3-certbot-nginx...'
    apt-get update && apt-get install -y python3-certbot-nginx
  fi

  # Ensure options-ssl-nginx.conf exists
  if [ ! -f '/etc/letsencrypt/options-ssl-nginx.conf' ]; then
    echo 'Downloading options-ssl-nginx.conf...'
    mkdir -p /etc/letsencrypt
    curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf -o /etc/letsencrypt/options-ssl-nginx.conf || true
  fi

  # Ensure ssl-dhparams.pem exists
  if [ ! -f '/etc/letsencrypt/ssl-dhparams.pem' ]; then
    echo 'Downloading ssl-dhparams.pem...'
    mkdir -p /etc/letsencrypt
    curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem -o /etc/letsencrypt/ssl-dhparams.pem || true
  fi

  if [ ! -d '/etc/letsencrypt/live/openroute.ir' ]; then
    echo 'SSL certificates for openroute.ir not found. Attempting certbot generation...'
    certbot certonly --nginx -d openroute.ir --non-interactive --agree-tos --register-unsafely-without-email || true
  fi
"

# 3. Copy the actual SSL reverse-proxy configuration to the VPS
sshpass -p '1272510662' scp -o StrictHostKeyChecking=no scratch/openroute.ir.conf root@212.74.39.79:/etc/nginx/sites-available/openroute.ir.conf

# 4. Reload Nginx to activate the SSL configuration
sshpass -p '1272510662' ssh -o StrictHostKeyChecking=no root@212.74.39.79 "
  echo 'Testing Nginx configuration...'
  nginx -t
  echo 'Restarting Nginx...'
  systemctl restart nginx
"

echo "=== DEPLOYMENT COMPLETED SUCCESSFULY ==="
