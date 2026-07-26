## What this is

A second, separate Raspberry Pi (hostname `philco`, currently `192.168.68.65`)
that lives in the same cabinet as the touchscreen UI Pi (`philco-ui`, see the
main [README.md](../README.md)) but runs none of this repo's code. Its only
job is to be a Bluetooth/AirPlay/Spotify Connect audio receiver for the
cabinet's speaker. Documented here (2026-07) after being rediscovered and
inspected — nobody remembered exactly how it was set up, so this is the
result of poking around on the device itself, not a build log written at
the time.

**It looked like it might be a prebuilt "radio" image (something like
moOde/Volumio/HiFiBerryOS) but it is not** — see "How we confirmed this"
below. It's stock Raspberry Pi OS with three off-the-shelf pieces
apt-installed on top.

## Hardware

- Raspberry Pi 3 Model A+
- HiFiBerry AMP2 HAT (I2S amplifier, drives speakers directly off the
  board) — `dtoverlay=hifiberry-amp2` and `dtparam=i2s=on` in
  `/boot/firmware/config.txt`
- ALSA output is pinned to this HAT via `/etc/asound.conf`
  (`pcm.!default`/`ctl.!default` → `hw:0`)

## Software stack

- **OS**: Raspberry Pi OS (Raspbian 12 "bookworm"), imaged 2025-11-23/24.
  Confirmed via `/etc/rpi-issue` ("Generated using pi-gen", the official
  Raspberry Pi OS build tool) and the standard `bootfs`/`rootfs` partition
  labels from Raspberry Pi Imager.
- **Spotify Connect**: `raspotify` (librespot wrapper), apt-installed
  2025-12-21 from its own repo (`dtcooper.github.io/raspotify` — added by
  raspotify's official one-line installer script).
- **AirPlay**: `shairport-sync`, apt-installed 2025-12-21 from the standard
  Debian/Raspberry Pi repos.
- **Bluetooth (A2DP)**: stock `bluez` + `pulseaudio-module-bluetooth`.
  Always discoverable/pairable (`DiscoverableTimeout=0`,
  `PairableTimeout=0`, `AutoEnable=true` in `/etc/bluetooth/main.conf`), so
  a phone can find and connect to it without anyone touching the device.
- **Custom auto-pair agent**: `/usr/local/bin/bt-agent.py`, run by
  `bt-agent.service` (`/etc/systemd/system/bt-agent.service`). A small
  BlueZ D-Bus agent that auto-accepts pairing requests with a hardcoded
  PIN (`9161`) instead of requiring an interactive prompt — this is what
  makes "just pair your phone" work with no keyboard/screen attached to
  this Pi. Not a real secret (Bluetooth PIN pairing isn't meant to be
  strong security, and this is a home speaker), but worth knowing it's
  there if this box or the script is ever reused somewhere pairing
  security actually matters.

All three sources (Spotify Connect, AirPlay, Bluetooth) end up going out
through the same ALSA device, so only one can realistically play at a time.

## How we confirmed this isn't a prebuilt image

- `/etc/rpi-issue` and `/etc/os-release` both identify it as plain
  Raspberry Pi OS — a dedicated distro (moOde, Volumio, RuneAudio,
  HiFiBerryOS, etc.) would report its own OS name here instead.
- `/etc/apt/sources.list.d/` has only the official Raspberry Pi repo and
  raspotify's own repo — no third-party image-vendor repo.
- `dpkg.log` shows `shairport-sync` and `raspotify` were both installed in
  a two-minute window on **2025-12-21**, about a month *after* the OS
  image's own build date (2025-11-23/24). If this were a single prebuilt
  image, those packages would carry the same build timestamp as the OS
  itself. Instead, someone flashed plain Raspberry Pi OS and then, weeks
  later, ran through raspotify's installer, `apt install shairport-sync`,
  and wrote the custom pairing agent — three separate manual steps, not
  one appliance flash. (Easy to misremember as prebuilt — raspotify's
  installer in particular is a single curl-pipe-bash command that feels
  like flashing an appliance.)

## Current health (as of 2026-07-26)

Unlike the UI Pi (see [scripts/pi-maintenance/](../scripts/pi-maintenance/)
for that incident), this one is healthy: 40% disk used, 4.0G free. It
hasn't been running unattended nearly as long. It has **not** yet had the
journald size cap / disk-space watchdog from `scripts/pi-maintenance/`
applied — same failure mode (unbounded journal growth over a year+ of
unattended uptime) could hit this box too given enough time. Worth
applying the same guardrails here preemptively rather than waiting for it
to happen again.

## Remote access

Uses the same toggleable `claude-agent` service account pattern as the UI
Pi — see [scripts/remote-access/](../scripts/remote-access/). Same
keypair is trusted on both machines; revocation is per-device via each
Pi's own `agent-access-off.sh`, so sharing the key doesn't reduce
isolation between the two boxes.
