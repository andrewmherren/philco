## Why this exists

Caps `systemd-journald`'s size and adds a periodic disk-space check,
because these devices run unattended for a year or more between visits —
without a cap, journald can quietly fill a small SD card over that much
uptime.

Built after a real incident (2026-07): `philco-ui`'s ~7.4G card
(non-expandable) filled to 100% — `systemd-journald` had no size cap, so
the persistent journal (`/var/log/journal/`) grew unbounded over a year+
of unattended uptime until it, along with the Arduino IDE install and
this repo's own checkout under `/home/philco`, ate the whole card. This
broke `sudo` and package installs and very nearly corrupted
`/etc/sudoers.d` mid-write.

Recovering also turned up two related, silently-broken services (most
likely side effects of running disk-full for a while): `systemd-timesyncd`
was crash-looping (`status=226/NAMESPACE`, consistent with a systemd
private-mount-namespace setup failing when the disk had no room), and
`/etc/resolv.conf` had been empty since first boot (dhcpcd's DNS record
wasn't being flushed to disk), which had silently broken both DNS and NTP
sync. Restarting `systemd-timesyncd` and `dhcpcd` resolved both once disk
space was available again — worth knowing if a Pi's clock or DNS ever
seem wrong for no reason: check `df -h /` first, even if the symptom
doesn't look disk-related. If DNS breaks again, check `cat /etc/resolv.conf`
and `sudo resolvconf -l` first — `resolvconf`/openresolv are installed and
work correctly when invoked, the issue was the record from dhcpcd not
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
3. **`go-librespot-restart.timer`** (weekly, radio Pi only — skipped by
   `install.sh` if `go-librespot.service` doesn't exist on the box) →
   `go-librespot-restart.service` → `systemctl restart go-librespot.service`.
   Belt-and-suspenders for a real incident (2026-09): after ~37 days of
   continuous uptime, go-librespot's Spotify Login5 token stopped
   renewing — the process still looked "alive" (could still reconnect at
   the lower AP level), but every play request silently failed. A plain
   restart fixed it instantly. See `radio-pi/README.md`'s Spotify Connect
   section for the full story; this timer just bounds how long a repeat
   of that (or anything like it) could go unnoticed to one week.

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
