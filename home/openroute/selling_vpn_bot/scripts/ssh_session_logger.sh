#!/bin/bash
# ssh_session_logger.sh
# Configure in /etc/pam.d/sshd:
# session optional pam_exec.so expose_authtok /usr/local/bin/ssh_session_logger.sh

# PAM provides these environment variables:
# $PAM_USER, $PAM_RHOST, $PAM_TYPE (open_session, close_session)

API_URL="http://YOUR_BACKEND_IP:8000/api/v1/servers/webhook/session"
SERVER_IP=$(hostname -I | awk '{print $1}') # Or read from a config file

if [ "$PAM_TYPE" == "open_session" ] || [ "$PAM_TYPE" == "close_session" ]; then
    curl -s -X POST $API_URL \
         -H "Content-Type: application/json" \
         -d "{
               \"server_ip\": \"$SERVER_IP\",
               \"username\": \"$PAM_USER\",
               \"remote_ip\": \"$PAM_RHOST\",
               \"event\": \"$PAM_TYPE\"
             }" > /dev/null
fi
