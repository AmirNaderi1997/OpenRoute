#!/bin/bash
set -euo pipefail

echo "Configuring remote VPN VPS for direct SSH links on port 443"

apt-get update
apt-get install -y python3 python3-venv python3-pip iptables

if ! grep -q "^Port 443$" /etc/ssh/sshd_config; then
  sed -i 's/^#\?Port .*/Port 443/' /etc/ssh/sshd_config || true
  if ! grep -q "^Port 443$" /etc/ssh/sshd_config; then
    echo "Port 443" >> /etc/ssh/sshd_config
  fi
fi

if grep -q "^#\?PasswordAuthentication" /etc/ssh/sshd_config; then
  sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config
else
  echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config
fi

if ! grep -q "^Match User openroute\\*" /etc/ssh/sshd_config; then
  cat >> /etc/ssh/sshd_config <<'EOF'
Match User openroute*
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding yes
EOF
fi

mkdir -p /opt/openroute
systemctl restart ssh || systemctl restart sshd

echo "Remote VPS configured."
