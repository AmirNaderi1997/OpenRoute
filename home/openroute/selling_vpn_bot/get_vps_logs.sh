#!/bin/bash
echo "=== 1. VPS Docker Containers ==="
sshpass -p '1272510662a' ssh -o StrictHostKeyChecking=no openroute@212.74.39.79 "docker ps"

echo "=== 2. VPS Nginx Configuration ==="
sshpass -p '1272510662' ssh -o StrictHostKeyChecking=no root@212.74.39.79 "cat /etc/nginx/sites-enabled/openroute.ir.conf"

echo "=== 3. openroute_web Container Logs ==="
sshpass -p '1272510662a' ssh -o StrictHostKeyChecking=no openroute@212.74.39.79 "docker logs --tail 30 openroute_web"

echo "=== 4. openroute_tunnel Container Logs ==="
sshpass -p '1272510662a' ssh -o StrictHostKeyChecking=no openroute@212.74.39.79 "docker logs --tail 30 openroute_tunnel"
