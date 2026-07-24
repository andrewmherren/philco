#!/bin/bash
# Full teardown of the account created by setup-service-account.sh —
# removes the user, home directory, and sudoers entry entirely.
#
# Usage:
#   sudo ./remove-service-account.sh
#   SERVICE_USER=my-agent sudo -E ./remove-service-account.sh
set -euo pipefail

SERVICE_USER="${SERVICE_USER:-claude-agent}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

pkill -u "$SERVICE_USER" 2>/dev/null || true

if id "$SERVICE_USER" >/dev/null 2>&1; then
    userdel -r "$SERVICE_USER"
else
    echo "User $SERVICE_USER does not exist, skipping."
fi

rm -f "/etc/sudoers.d/$SERVICE_USER"
rm -f "/usr/local/sbin/agent-access-on.sh" "/usr/local/sbin/agent-access-off.sh"

echo "Removed $SERVICE_USER, its sudoers entry, and the toggle scripts."
