## Why this exists

In 2026-07 this Pi's SD card (~7.4G, non-expandable) filled to 100%, which
broke `sudo`, package installs, and very nearly corrupted `/etc/sudoers.d`
mid-write. Root cause: this device runs unattended for a year or more
between visits, and `systemd-journald` had no size cap, so the persistent
journal (`/var/log/journal/`) grew unbounded over that time until it — along
with the Arduino IDE install and the project checkout under `/home/philco`
— ate the whole card.

At the same time we found two related, silently-broken services on this
specific Pi (most likely from whatever happened during the disk-full
period): `systemd-timesyncd` was crash-looping (`status=226/NAMESPACE`,
consistent with a systemd private-mount-namespace setup failing when the
disk had no room), and `/etc/resolv.conf` had been empty since first boot,
so DNS resolution silently failed — which in turn kept NTP from ever
completing a sync. Restarting `systemd-timesyncd` and `dhcpcd` (see
2026-07 fix in git history / this file) resolved both once disk space was
available again. If DNS breaks again, check `cat /etc/resolv.conf` and
`sudo resolvconf -l` first — `resolvconf`/openresolv are installed and work
correctly when invoked, the issue was that the record from dhcpcd wasn't
being flushed to disk.

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
