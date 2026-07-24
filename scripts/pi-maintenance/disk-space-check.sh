#!/bin/bash
# Weekly safety net: if the root filesystem is getting critically full,
# vacuum logs/caches automatically and log a warning so a problem doesn't
# silently accumulate for months between someone actually looking at this Pi.
#
# Installed by install.sh as /usr/local/sbin/disk-space-check.sh, run by
# disk-space-check.timer. See scripts/pi-maintenance/README.md.
set -euo pipefail

THRESHOLD=90
USE="$(df --output=pcent / | tail -1 | tr -dc '0-9')"

if [ "$USE" -ge "$THRESHOLD" ]; then
    logger -t disk-space-check "WARNING: / is at ${USE}% - running emergency cleanup"
    journalctl --vacuum-size=20M || true
    apt-get clean || true
    logger -t disk-space-check "Cleanup done, / now at $(df --output=pcent / | tail -1 | tr -dc '0-9')%"
fi
