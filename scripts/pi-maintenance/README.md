## Why this exists

Caps `systemd-journald`'s size and adds a periodic disk-space check,
because these devices run unattended for a year or more between visits —
without a cap, journald can quietly fill a small SD card over that much
uptime. Full incident history and root-cause details (including a DNS/NTP
issue that surfaced alongside it) are in
[AGENT_SCRATCHPAD.md](../../AGENT_SCRATCHPAD.md) at the repo root.

## What this installs

Run once per Pi (or after a fresh image):

```
sudo ./install.sh
```

This installs:

1. **`/etc/systemd/journald.conf.d/10-disk-cap.conf`** — caps the
   persistent journal at 100M total (20M per file, 3 month retention). This
   is the actual fix for the original problem: without a cap, journald will
   happily use up to 10% of the filesystem by default, and on a ~7G card
   that's still a meaningful chunk, with no guarantee it stays there if
   defaults change.
2. **`disk-space-check.timer`** (weekly) → `disk-space-check.service` →
   `/usr/local/sbin/disk-space-check.sh` — a belt-and-suspenders check: if
   `/` is ever at 90%+ usage, it runs `journalctl --vacuum-size=20M` and
   `apt-get clean`, and logs a warning via `logger` (visible in
   `journalctl -t disk-space-check`) so there's at least a trace of it
   having happened. This exists because the whole point of this device is
   that nobody looks at it for a year at a time — the journald cap should
   be sufficient on its own, but this catches anything else that grows
   unexpectedly (npm/apt caches from a future maintenance session, browser
   profile data, etc.) before it becomes a repeat of the 100%-full incident.

## Checking on it later

```
df -h /                                  # overall usage
journalctl --disk-usage                  # journal size (should stay <=100M)
systemctl list-timers disk-space-check.timer
journalctl -t disk-space-check           # history of any emergency cleanups
timedatectl                              # clock should show "synchronized: yes"
cat /etc/resolv.conf                     # should list nameservers, not be empty
```

## Reusing this in another project

Same idea applies to any low-maintenance/unattended Linux box: cap
`journald` explicitly (don't rely on defaults) and add a cheap periodic
"if things go sideways, do something about it before the disk fills"
check. Copy this directory, adjust the threshold/paths in
`disk-space-check.sh` if the device isn't running Debian/apt, and run
`install.sh`.
