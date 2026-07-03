#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== Reading ssh_443_mux.py from VPS ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "cat /opt/vpn_manager/ssh_443_mux.py"
