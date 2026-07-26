## Picking this project back up after a long gap

Read [AGENT_SCRATCHPAD.md](AGENT_SCRATCHPAD.md) first — current status,
what's done, what's pending, and debugging history all live there. If
something seems broken, `df -h /`, `timedatectl`, and
`cat /etc/resolv.conf` are good first checks (see
[scripts/pi-maintenance/](scripts/pi-maintenance/) for why).

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

## Temporary remote access for AI-assisted debugging

See [scripts/remote-access/](scripts/remote-access/) for a scoped,
key-only, one-command-toggle SSH account you can hand to an AI assistant
(or anyone else) without exposing your own login — and revoke just as
easily when the session's over.

## Radio stack revamp (in progress, `revamp` branch)

See [radio-stack/README.md](radio-stack/README.md) for the project plan
to unify the audio/Bluetooth/Spotify/HA stack across this device and any
future ones.

## The second Pi (Bluetooth/AirPlay/Spotify radio)

This repo's app runs on `philco-ui`, but the cabinet also has a second,
separate Raspberry Pi (`philco`) that runs none of this code — it's just a
Bluetooth/AirPlay/Spotify Connect audio receiver. See
[radio-pi/README.md](radio-pi/README.md) for how it's actually put
together (spoiler: not a prebuilt image, despite looking like one).
