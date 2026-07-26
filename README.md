## Setup
* Copy assets/config.txt to /boot/config.txt for touch screen config (verify compatibility if raspbian other than buster)
* Copy assets/input.conf to /usr/share/X11/xorg.conf.d/input.conf for touch calibration. New calibration can be made from menu > preferences > calibrate touch
* run `uname -r` to see which arm version raspi has.
* Go to nodejs.org and download node for arm version above.
* run `tar -xvf node...`
* Then copy binaries with "suco cp -R node-v6.../* /usr/local
* then run the setups script `/scripts/setups.sh`
* Disable screen power of in preferences > screen saver
* Finally pair bluetooth keyboard using bluetooth symbol in task bar.
* Go to https://www.arduino.cc/en/Main/Software
* download the Linux 32-bit arm version
* `cd~/Downloads`
* `tar -xvf arduino-1...`
* `sudo mv arduino-1... /etc/arduino`
* `sudo /etc/arduino/install.sh`
* Goto https://www.pjrc.com/teensy/teensyduino.html and download teensyduino for arm 32-bit and linux udev rules (follow install instructions on site)

## Known constraints

* The Pi's SD card is small (~7.4G total, `/dev/mmcblk0p2` is the whole
  card — nothing to expand). It runs close to full even at rest between the
  OS, Arduino IDE under `/etc/arduino` (~860M, per the setup steps above),
  and `/home/philco` (~830M). Before installing anything new, check
  `df -h /` first; `sudo journalctl --vacuum-size=50M` and `sudo apt clean`
  are quick, safe ways to claw back space if a command fails with
  "No space left on device". A bigger card is the real long-term fix if this
  becomes a recurring problem.

## Temporary remote access for AI-assisted debugging

See [scripts/remote-access/](scripts/remote-access/) for a scoped,
key-only, one-command-toggle SSH account you can hand to an AI assistant
(or anyone else) without exposing your own login — and revoke just as
easily when the session's over.

## The second Pi (Bluetooth/AirPlay/Spotify radio)

This repo's app runs on `philco-ui`, but the cabinet also has a second,
separate Raspberry Pi (`philco`) that runs none of this code — it's just a
Bluetooth/AirPlay/Spotify Connect audio receiver. See
[radio-pi/README.md](radio-pi/README.md) for how it's actually put
together (spoiler: not a prebuilt image, despite looking like one).

## Disk-space guardrails (2026-07 incident)

The SD card filled to 100% after roughly a year of unattended uptime,
which nearly corrupted `sudo` itself. Root cause and the fix (a journald
size cap + a weekly watchdog timer, plus two related broken services —
NTP sync and DNS — that surfaced during cleanup) are documented in
[scripts/pi-maintenance/](scripts/pi-maintenance/). If you're picking
this project back up after a long gap and something seems broken, read
that first — `df -h /`, `timedatectl`, and `cat /etc/resolv.conf` are
good first checks.
