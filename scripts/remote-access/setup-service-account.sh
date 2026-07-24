#!/bin/bash
# One-time setup of a locked-down, key-only, easy-to-toggle SSH account for
# an AI assistant or other third party. See README.md in this directory.
#
# Usage:
#   sudo ./setup-service-account.sh "ssh-ed25519 AAAA... key-comment"
#   SERVICE_USER=my-agent sudo -E ./setup-service-account.sh "ssh-ed25519 AAAA..."
set -euo pipefail

SERVICE_USER="${SERVICE_USER:-claude-agent}"
PUBKEY="${1:-}"

if [ -z "$PUBKEY" ]; then
    echo "Usage: sudo $0 \"<ssh public key>\"" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

if id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "User $SERVICE_USER already exists, skipping account creation."
else
    adduser --disabled-password --gecos "" "$SERVICE_USER"
    usermod -aG sudo "$SERVICE_USER"
fi

SUDOERS_FILE="/etc/sudoers.d/$SERVICE_USER"
echo "$SERVICE_USER ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"
if ! visudo -c >/dev/null; then
    echo "sudoers validation failed after writing $SUDOERS_FILE — removing it." >&2
    rm -f "$SUDOERS_FILE"
    exit 1
fi

passwd -l "$SERVICE_USER"

HOME_DIR="/home/$SERVICE_USER"
mkdir -p "$HOME_DIR/.ssh"
touch "$HOME_DIR/.ssh/authorized_keys"
chown -R "$SERVICE_USER:$SERVICE_USER" "$HOME_DIR/.ssh"
chmod 700 "$HOME_DIR/.ssh"
chmod 600 "$HOME_DIR/.ssh/authorized_keys"

echo "$PUBKEY" > "$HOME_DIR/agent_pubkey.txt"
chown "$SERVICE_USER:$SERVICE_USER" "$HOME_DIR/agent_pubkey.txt"

ON_SCRIPT="/usr/local/sbin/agent-access-on.sh"
OFF_SCRIPT="/usr/local/sbin/agent-access-off.sh"

cat > "$ON_SCRIPT" <<EOF
#!/bin/bash
cp "$HOME_DIR/agent_pubkey.txt" "$HOME_DIR/.ssh/authorized_keys"
chown $SERVICE_USER:$SERVICE_USER "$HOME_DIR/.ssh/authorized_keys"
chmod 600 "$HOME_DIR/.ssh/authorized_keys"
echo "$SERVICE_USER access ENABLED"
EOF

cat > "$OFF_SCRIPT" <<EOF
#!/bin/bash
> "$HOME_DIR/.ssh/authorized_keys"
echo "$SERVICE_USER access DISABLED"
EOF

chmod 700 "$ON_SCRIPT" "$OFF_SCRIPT"

echo "Setup complete for user '$SERVICE_USER'."
echo "Access is currently DISABLED. Enable with: sudo $ON_SCRIPT"
