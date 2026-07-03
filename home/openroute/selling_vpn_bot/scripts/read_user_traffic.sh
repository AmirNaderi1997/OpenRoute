#!/bin/bash
# read_user_traffic.sh
# Usage: ./read_user_traffic.sh <username> [--reset]

USERNAME=$1
RESET_FLAG=$2

if [ -z "$USERNAME" ]; then
    echo '{"error": "Username required"}'
    exit 1
fi

# Read the exact byte count from the chain
# -x: exact values, -v: verbose (shows bytes), -n: numeric
CHAIN="VPN_USER_$USERNAME"
BYTES=$(iptables -L $CHAIN -x -v -n 2>/dev/null | grep 'RETURN' | awk '{print $2}')

if [ -z "$BYTES" ]; then
    BYTES=0
fi

# Output as JSON
echo "{\"username\": \"$USERNAME\", \"bytes_used\": $BYTES}"

# Reset counters if requested
if [ "$RESET_FLAG" == "--reset" ]; then
    iptables -Z $CHAIN
fi
