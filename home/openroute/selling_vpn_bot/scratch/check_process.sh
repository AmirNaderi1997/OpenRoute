#!/bin/bash
VPS_IP="212.74.39.79"
ROOT_PASS="1272510662"

echo "=== Checking command line of PID 55190 ==="
sshpass -p "$ROOT_PASS" ssh -o StrictHostKeyChecking=no root@$VPS_IP "ps -fp 55190 || cat /proc/55190/cmdline | tr '\0' ' '"
echo -e "\n"
