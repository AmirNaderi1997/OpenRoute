#!/bin/bash
set -e

VPS_IP="66.92.161.177"
VPS_USER="root"
VPS_PASS="1272510662"
VPS_SSH_PORT="22"
TARGET_DIR="/root/selling_vpn_bot"

echo "=========================================="
echo "   Initiating Deployment to VPS"
echo "=========================================="

# 1. Setup local env file for deployment
if [ -f .env.production ]; then
    cp .env.production .env
    echo "✅ Cloned .env.production to .env for deployment"
else
    echo "❌ .env.production not found!"
    exit 1
fi

# 2. SSH into VPS to install Docker if missing
echo "🛠️  Checking/Installing Docker on remote VPS..."
sshpass -p "$VPS_PASS" ssh -p "$VPS_SSH_PORT" -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP << 'EOF'
    if ! command -v docker &> /dev/null; then
        echo "Docker not found. Installing..."
        apt-get update
        apt-get install -y apt-transport-https ca-certificates curl software-properties-common rsync
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
        add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" -y
        apt-get update
        apt-get install -y docker-ce docker-compose-plugin docker-compose
    else
        echo "Docker is already installed."
    fi
    mkdir -p /root/selling_vpn_bot
EOF

# 3. Build the webapp frontend
if [ -d "webapp" ] && [ -f "webapp/package.json" ]; then
    echo "🔧 Building webapp frontend..."
    cd webapp
    npm install --legacy-peer-deps
    npm run build
    cd ..
    echo "✅ Webapp built successfully."
else
    echo "⚠️  webapp directory not found, skipping frontend build."
fi

# 4. Rsync files to VPS
echo "🚀 Syncing files via rsync..."
sshpass -p "$VPS_PASS" rsync -avz -e "ssh -p $VPS_SSH_PORT -o StrictHostKeyChecking=no" \
    --exclude '.git' --exclude 'node_modules' --exclude 'venv' --exclude '__pycache__' \
    --exclude 'backups' \
    ./ $VPS_USER@$VPS_IP:$TARGET_DIR/

# 5. Build and run Docker containers on VPS
echo "🐳 Starting Docker containers on remote VPS..."
sshpass -p "$VPS_PASS" ssh -p "$VPS_SSH_PORT" -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP << 'EOF'
    cd /root/selling_vpn_bot
    docker compose -f docker-compose.prod.yml down
    docker compose -f docker-compose.prod.yml up -d --build
    
    # Restart the tunnel proxy service to load new connection limiting features
    echo "🔄 Restarting tunnel proxy service on host..."
    systemctl daemon-reload
    systemctl restart tunnel
EOF

echo "=========================================="
echo "🎉 Deployment Successful! The project is online."
echo "=========================================="
