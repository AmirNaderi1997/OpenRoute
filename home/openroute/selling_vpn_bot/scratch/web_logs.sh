#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== openroute_web Container Logs ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "docker logs openroute_web --tail 100"
