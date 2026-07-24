#!/bin/bash
# Installs the disk-space guardrails documented in scripts/pi-maintenance/README.md:
#   1. A journald drop-in that caps the persistent journal size.
#   2. A weekly systemd timer that vacuums logs/caches if / is critically full.
#
# Usage:
#   sudo ./install.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -D -m 644 "$DIR/10-disk-cap.conf" /etc/systemd/journald.conf.d/10-disk-cap.conf
systemctl restart systemd-journald

install -m 755 "$DIR/disk-space-check.sh" /usr/local/sbin/disk-space-check.sh
install -m 644 "$DIR/disk-space-check.service" /etc/systemd/system/disk-space-check.service
install -m 644 "$DIR/disk-space-check.timer" /etc/systemd/system/disk-space-check.timer
systemctl daemon-reload
systemctl enable --now disk-space-check.timer

echo "Installed journald cap and disk-space-check.timer."
journalctl --disk-usage
systemctl list-timers disk-space-check.timer --no-pager
