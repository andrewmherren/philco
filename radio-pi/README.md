## What this is

A second, separate Raspberry Pi (hostname `philco`, `192.168.68.65`) that
lives in the same cabinet as the touchscreen UI Pi (`philco-ui`, see the
main [README.md](../README.md)) but runs none of this repo's code. Its job
is to be a Bluetooth/AirPlay/Spotify Connect audio receiver for the
cabinet's speaker. It is **not** a prebuilt "radio" image — it's stock
Raspberry Pi OS with a few things installed on top.

## Hardware

- Raspberry Pi 3 Model A+
- HiFiBerry AMP2 HAT (I2S amplifier, drives speakers directly off the
  board) — `dtoverlay=hifiberry-amp2` and `dtparam=i2s=on` in
  `/boot/firmware/config.txt`
- ALSA output pinned to this HAT via `/etc/asound.conf`

## Software stack

- **OS**: Raspberry Pi OS (Raspbian 12 "bookworm")
- **Spotify Connect**: [`go-librespot`](https://github.com/devgianlu/go-librespot),
  config at `/etc/go-librespot/config.yml`, run by `go-librespot.service`
- **AirPlay**: `shairport-sync`
- **Bluetooth (A2DP)**: `bluez` + PipeWire's Bluetooth module. Always
  discoverable/pairable, but completing a pairing requires confirming a
  code shown on `philco-ui`'s touchscreen — see "Pairing a device" below
- **Pairing agent**: [`bt-agent.py`](bt-agent.py), run by
  [`bt-agent.service`](bt-agent.service)
- **Volume ceiling**: hardware gain register capped so nothing can play
  dangerously loud — see "Adjusting max volume" below
- **Equalizer**: `libasound2-plugin-equal` (alsaequal), a 10-band ALSA
  EQ sitting in front of `hw:0` for all sources — see "Equalizer" below

All sources share the same ALSA output, so only one plays at a time.

## Pairing a device

The radio is always discoverable. Start pairing from your phone as
normal — a code will appear on `philco-ui`'s touchscreen with **Pair**
and **Cancel** buttons. Pairing only completes if someone taps **Pair**
on that screen; tapping Cancel (or doing nothing) rejects it, even if the
phone side shows "confirmed."

Devices that are already paired can reconnect anytime without needing
this again.

## Adjusting max volume

```
sudo amixer -c0 sset Digital <N>%,<N>%   # e.g. 70%; lower = quieter
sudo alsactl store                        # persist across reboots
```
Change is live — no restart needed to test. `amixer -c0 sget Digital`
shows the current setting. This is a hardware ceiling, not a day-to-day
control — see "Spotify volume knob" below for that.

## Spotify volume knob

`philco-ui`'s physical volume knob is wired to Spotify's own volume only
(via [`spotify-volume-agent.py`](spotify-volume-agent.py) /
[`spotify-volume-agent.service`](spotify-volume-agent.service), POSTing
to `go-librespot`'s local API at `127.0.0.1:3678`). Changing volume from
the Spotify app itself works too and takes effect immediately — both
just set the same underlying value, so whichever was touched last is in
effect, with no extra logic needed. AirPlay and Bluetooth volume are
deliberately left alone; each is controlled solely by whatever's
connected to it.

## Equalizer

A 10-band ALSA equalizer sits in the audio path for all sources, to
compensate for the muddy midrange the current 3D-printed speaker
enclosures produce. Controlled remotely from `philco-ui`'s touchscreen
(turn the mode switch to position 6) via [`eq-agent.py`](eq-agent.py) /
[`eq-agent.service`](eq-agent.service) — same MQTT-agent pattern as
[`bt-agent.py`](bt-agent.py).

To adjust a band by hand instead:
```
alsamixer -D eq
# or non-interactively, e.g.:
amixer -D eq cset numid=4 40,40   # numid=4 is the 250 Hz band
```
Changes made this way aren't reflected on the touchscreen and won't
survive a reboot — use the touchscreen (or publish to
`philco/eq/set/<band>` over MQTT) for anything that should stick.

## Remote access

Same toggleable `claude-agent` SSH account as the UI Pi — see
[scripts/remote-access/](../scripts/remote-access/).

## More detail

Root causes, debugging history, gotchas, and current open issues (e.g.
Bluetooth pairing works but audio doesn't route through the speaker yet)
are in [AGENT_SCRATCHPAD.md](../AGENT_SCRATCHPAD.md) at the repo root,
not here — this file stays a quick human-facing reference.
