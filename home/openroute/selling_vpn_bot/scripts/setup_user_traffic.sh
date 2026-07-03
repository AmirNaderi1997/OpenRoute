#!/bin/bash
# setup_user_traffic.sh
# Usage: ./setup_user_traffic.sh <username> <uid>

USERNAME=$1
USER_UID=$2

if [ -z "$USERNAME" ] || [ -z "$USER_UID" ]; then
    echo "Usage: $0 <username> <uid>"
    exit 1
fi

# Create a custom chain for the user if it doesn't exist
iptables -N VPN_USER_$USERNAME 2>/dev/null

# Flush it to ensure idempotency
iptables -F VPN_USER_$USERNAME

# Add rules to count traffic matching the UID
# Outbound traffic (Downloads for the VPN user)
iptables -A VPN_USER_$USERNAME -m owner --uid-owner $USER_UID -j RETURN

# Link the custom chain to the OUTPUT chain if not already linked
iptables -C OUTPUT -j VPN_USER_$USERNAME 2>/dev/null || iptables -A OUTPUT -j VPN_USER_$USERNAME

echo "Traffic tracking initialized for $USERNAME (UID: $USER_UID)"
