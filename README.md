## Picking this project back up after a long gap

This project gets touched once every year or two — start with this file
and [radio-pi/README.md](radio-pi/README.md) (for the second Pi) for how
things are currently put together. If something seems broken, `df -h /`,
`timedatectl`, and `cat /etc/resolv.conf` are good first checks (see
[scripts/pi-maintenance/](scripts/pi-maintenance/) for why) — and if
`go-librespot` looks connected (track changes visible on a phone) but no
audio plays, especially right after a router/ISP change, try
`sudo systemctl restart go-librespot.service` on the radio Pi before
digging deeper (a long-running network daemon can hold onto stale
DNS/connection state across an ISP change).

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

* The Pi's SD card is small (~7.4G, non-expandable) and runs close to
  full even at rest. Check `df -h /` before installing anything new — see
  [scripts/pi-maintenance/](scripts/pi-maintenance/) for guardrails and
  quick-relief commands if a command fails with "No space left on device".

## Operational gotchas

* **`api/` and `ui/` are not systemd units** — LXDE autostart launches
  them once (`npm start` in each directory) when the desktop session
  starts. After a code change, restart `api/` by hand:
  ```
  sudo pkill -u philco -f server.js
  sudo -u philco bash -c 'cd /home/philco/philco/api && nohup npm start > /tmp/api-test.log 2>&1 & disown'
  ```
* **The dev server's hot-reload doesn't actually reach the open kiosk
  tab.** Neither `entry.jsx` nor `App.jsx` has a `module.hot.accept()`
  call, so `webpack-hot-middleware` recompiles correctly in the
  background but the already-open Chromium tab never re-fetches it —
  looks like nothing happened. Force a refresh remotely:
  ```
  sudo apt-get install -y xdotool   # one-time
  sudo -u philco env DISPLAY=:0 XAUTHORITY=/home/philco/.Xauthority xdotool key F5
  ```
* **Editing a root-owned `600` file (e.g. an `.env`) with `vi` but
  without `sudo`** silently opens an empty new buffer rather than
  erroring — don't mistake that for the real file being empty or lost.

## Temporary remote access for AI-assisted debugging

See [scripts/remote-access/](scripts/remote-access/) for a scoped,
key-only, one-command-toggle SSH account you can hand to an AI assistant
(or anyone else) without exposing your own login — and revoke just as
easily when the session's over.

## Radio stack revamp (in progress, `revamp` branch)

See [radio-stack/README.md](radio-stack/README.md) for the project plan
to unify the audio/Spotify/HA stack across this device and any future
ones.

## The second Pi (the radio)

This repo's app runs on `philco-ui`, but the cabinet also has a second,
separate Raspberry Pi (`philco`) that runs none of this code — it's a
Spotify Connect / Bluetooth / AirPlay audio receiver. See
[radio-pi/README.md](radio-pi/README.md) for how it's actually put
together (spoiler: not a prebuilt image, despite looking like one).
