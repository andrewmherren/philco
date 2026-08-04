## What this is

A second, separate Raspberry Pi (hostname `philco`, `192.168.68.65`) that
lives in the same cabinet as the touchscreen UI Pi (`philco-ui`, see the
main [README.md](../README.md)) but runs none of this repo's code. Its job
is to be a Spotify Connect audio receiver for the cabinet's speaker. It is
**not** a prebuilt "radio" image — it's stock Raspberry Pi OS with a few
things installed on top.

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
- **Volume ceiling**: hardware gain register capped so nothing can play
  dangerously loud — see "Adjusting max volume" below
- **Equalizer**: `libasound2-plugin-equal` (alsaequal), a 10-band ALSA
  EQ sitting in front of `hw:0` for all sources — see "Equalizer" below

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
effect, with no extra logic needed. Turning the knob down to off fully
stops Spotify (not just pauses) — turning it back on resumes playback
automatically via the station dial's current position, with no need to
reselect "philco" as the output device on your phone/computer.

## Station dial

The tuning-dial knob on `philco-ui` splits its usable range into equal
"stations," one per entry in `/etc/philco-station/regions.json` — the
count isn't fixed, so adding/removing entries there just makes each
station narrower/wider to fit the same physical sweep. Each station is
independently configured as either a specific Spotify URI
(playlist/album/track/artist — starts in shuffle) or quiet background
"static." One region is flagged `"default": true` and starts playing
automatically as soon as [`station-agent.py`](station-agent.py) /
[`station-agent.service`](station-agent.service) boots — no dial movement
required, just like a real radio powering on. Moving the dial to another
station takes over the shared audio output the same way any other source
does; turning it back and forth quickly between two static gaps doesn't
restart the noise, but moving between two different stations does switch
content immediately. Turning the volume knob down to off pauses playback
(including static) and pauses the mode switch too; turning it back on
resumes whatever station the dial is currently on. While off, moving the
dial or mode switch does nothing at all — `api/server.js` doesn't even
publish those changes while it knows the radio is off, so nothing
downstream can react to them.

This dial's potentiometer doesn't span the ADC's full theoretical range
the way the volume knob's does — its calibration
(`STATION_RAW_MIN`/`STATION_RAW_MAX` in `station-agent.py`, mirrored in
`api/server.js` for the touchscreen pointer) is a hardware constant, not
something to edit casually; see `AGENT_SCRATCHPAD.md` if the dial ever
seems to stop short of reaching all the stations again.

To change what's assigned to a station, or add/remove stations entirely,
edit `/etc/philco-station/regions.json` (see
[`station-regions.example.json`](station-regions.example.json) for the
shape — ship it with `REPLACE_ME` placeholder URIs, so it must be edited
with real ones before this does anything useful) and restart the
service — a restart is required to pick up a changed region count, this
isn't hot-reloaded:
```
sudo systemctl restart station-agent.service
```

## Equalizer

A 10-band ALSA equalizer sits in the audio path for all sources, to
compensate for the muddy midrange the current 3D-printed speaker
enclosures produce. Controlled remotely from `philco-ui`'s touchscreen
(turn the mode switch to position 6) via [`eq-agent.py`](eq-agent.py) /
[`eq-agent.service`](eq-agent.service).

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

Root causes, debugging history, gotchas, and current open issues are in
[AGENT_SCRATCHPAD.md](../AGENT_SCRATCHPAD.md) at the repo root, not here
— this file stays a quick human-facing reference.
