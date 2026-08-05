## What this is

A second, separate Raspberry Pi (hostname `philco`, `192.168.68.65`) that
lives in the same cabinet as the touchscreen UI Pi (`philco-ui`, see the
main [README.md](../README.md)) but runs none of this repo's code. Its job
is to be a Spotify Connect / Bluetooth / AirPlay audio receiver for the
cabinet's speaker. It is **not** a prebuilt "radio" image — it's stock
Raspberry Pi OS with a few things installed on top (see "How we confirmed
this isn't a prebuilt image" below).

## Hardware

- Raspberry Pi 3 Model A+
- HiFiBerry AMP2 HAT (I2S amplifier, drives speakers directly off the
  board) — `dtoverlay=hifiberry-amp2` and `dtparam=i2s=on` in
  `/boot/firmware/config.txt`
- ALSA output pinned to this HAT via `/etc/asound.conf`
  (`pcm.!default`/`ctl.!default` → `hw:0`)

## Software stack

- **OS**: Raspberry Pi OS (Raspbian 12 "bookworm")
- **Spotify Connect**: [`go-librespot`](https://github.com/devgianlu/go-librespot),
  config at `/etc/go-librespot/config.yml`, run by `go-librespot.service`
- **Bluetooth (A2DP)**: `bluez` for pairing/connections, `bluez-alsa`
  (`bluealsa` + `bluealsa-aplay`) to get the actual audio into ALSA —
  see "Bluetooth" below
- **AirPlay**: `shairport-sync`, config at `/etc/shairport-sync.conf` —
  see "AirPlay" below
- **Volume ceiling**: hardware gain register capped so nothing can play
  dangerously loud — see "Adjusting max volume" below
- **Equalizer**: `libasound2-plugin-equal` (alsaequal), a 10-band ALSA
  EQ sitting in front of `hw:0` for all sources — see "Equalizer" below

## Setting up go-librespot from scratch

`go-librespot` was chosen over the simpler `raspotify` package because
`raspotify` only ran in Spotify's Zeroconf/discovery mode — invisible to
Home Assistant's Spotify integration (which queries Spotify's Web API
device list, not local mDNS) unless something on the LAN actively
"woke" it first. `go-librespot` keeps a real persistent login instead, so
it's always visible to HA. If this ever needs to be rebuilt (new SD card,
replacement device, etc.):
1. Download the release asset for Raspberry Pi OS:
   `*_armv6_rpi.tar.gz` from
   [github.com/devgianlu/go-librespot/releases](https://github.com/devgianlu/go-librespot/releases)
   (works fine on 32-bit `armv7l` too — Go ARM builds are backwards
   compatible).
2. Config at `/etc/go-librespot/config.yml`: `audio_backend: alsa`,
   `audio_device: default`, `credentials.type: interactive`,
   `zeroconf_enabled: true`, `device_name: philco`.
3. `go-librespot.service` needs `Environment=HOME=/root` explicitly —
   without it, the binary fails with `"neither $XDG_CONFIG_HOME nor
   $HOME are defined"` even when `--config_dir` is passed, since bare
   systemd units don't populate `$HOME` on their own.
4. First run needs a one-time interactive OAuth login: start the binary
   and it prints a `https://accounts.spotify.com/authorize?...` URL with
   a `redirect_uri=http://127.0.0.1:<random-port>/login`. Open that URL
   in any browser signed into the Spotify account you want (same account
   Home Assistant's Spotify integration should use) — it'll redirect to
   `127.0.0.1:<port>` and fail to load in your browser (that address
   means "whichever machine opened the link," not the Pi — this is
   expected). Copy the failed URL's full query string and `curl` it
   *from an SSH session on the Pi itself* to deliver the code to the
   daemon's local callback listener. Credentials are cached afterward and
   reused silently on every future start/reboot — this step is only
   needed once, ever, unless the credentials cache is wiped.

## Adjusting max volume

This is a **hardware ceiling**, separate from and layered underneath the
day-to-day volume knob (see "Spotify volume knob" below) — nothing else
(`go-librespot`, `bluealsa`, `shairport-sync`) touches this control, they
all do their own volume purely in software *above* it, so this is the one
place that can never be exceeded regardless of source or app-side volume.
It exists because the HiFiBerry AMP2's gain register defaults to full
(0dB, no attenuation), which is genuinely dangerously loud for the
speakers in this cabinet.

Check the current level:
```
sudo amixer -c0 sget Digital
```
Change it:
```
sudo amixer -c0 sset Digital <N>%,<N>%   # e.g. 70%; lower = quieter, higher = louder
sudo alsactl store                        # persist across reboots (auto-reapplied by alsa-restore.service)
```
Change is live — no restart needed to test, only `alsactl store` once
you're happy with a level. The register is linear, 0.5dB per step over
0–207 steps (so roughly 2% ≈ 1dB) — `207/207` (100%) is 0dB/no
attenuation (max, avoid), `0/207` is silence. As of 2026-08-04 this was
set to **67% (139/207, -34dB)** — a fairly deep cut; if it's sounding too
quiet, raising it in small steps (e.g. try 80% ≈ -21dB) and listening at
a normal distance from the speaker is the way to dial it in — there's no
"correct" number, just "as loud as feels safe for these speakers."

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
something to edit casually — if the dial ever seems to stop short of
reaching all the stations again, that pair is the first thing to
re-measure (a full physical sweep, reading the raw values `server.js`
logs) rather than assume the config is wrong.

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

## Bluetooth

Bluetooth is entirely gated by the volume knob, via
[`bluetooth-agent.py`](bluetooth-agent.py) /
[`bluetooth-agent.service`](bluetooth-agent.service): the adapter is
powered off (undiscoverable, unpairable, unconnectable) whenever the knob
is off, and powered on — discoverable and pairable — as soon as it's on.
Turning the knob off disconnects any currently-connected phone too
(powering off the adapter does this automatically). No manual
"pairing mode" button or timer — as long as the radio is on, it's
pairable.

Pairing is zero-friction on purpose: no code to type or confirm on either
side ("Just Works" pairing), and a device is auto-trusted as soon as it
pairs once, so every future reconnection — any time it's back in range
while the radio is on — is automatic too. The only real security boundary
here is physical: a phone can only find or pair with the radio while
someone has the volume on.

**Gotcha if pairing ever fails with a generic "unsuccessful" message and
no useful log on either the radio or the pairing agent**: BlueZ refuses
to silently re-pair a device it already has an old key for via Just
Works (anti-downgrade-attack protection) — rejected at the kernel/mgmt
level before the pairing agent is even consulted, which is why nothing
useful shows up in its log. This is a real, hit-in-practice failure mode
(not hypothetical) whenever a phone and the radio end up with an
asymmetric bond state — an interrupted pairing attempt, the phone
forgetting the device, or this SD card ever getting restored from an
older backup. Fix, both device-only settings not tracked in this repo:
remove the stale record (`sudo rm -rf
/var/lib/bluetooth/<adapter-mac>/<phone-mac>/`, found via `bluetoothctl
devices` or by matching the phone's MAC) and confirm
`/etc/bluetooth/main.conf`'s `[General]` section has
`JustWorksRepairing = always` (not the Raspbian default, `never`) so this
can't recur for *any* device. If a failure like this ever needs deeper
diagnosis, `bluetoothd`'s own journal is often useless (as above) — a raw
capture, `sudo btmon -w /tmp/capture.log` (run it for several minutes,
pairing attempts happen fast but getting to the physical radio to
attempt one doesn't), read back with `sudo btmon -r /tmp/capture.log`,
shows the actual HCI/mgmt-layer conversation regardless of whether
`bluetoothd`'s business logic ever got involved.

Actual audio comes from `bluealsa` + `bluealsa-aplay`
(`bluealsa.service` / `bluealsa-aplay.service`, both from the
`bluez-alsa-utils` package), which pipe A2DP audio from whatever phone is
connected straight into the same shared ALSA `default` device
`go-librespot`/`sox`/`shairport-sync` use — same EQ, same hardware volume
ceiling. Only one source can hold that device at a time (no dmix), and
whichever one most recently started wins — see "Source arbitration"
below for the full three-way picture with AirPlay.

## AirPlay

Same volume-gating rule as Bluetooth, via
[`airplay-agent.py`](airplay-agent.py) /
[`airplay-agent.service`](airplay-agent.service): `shairport-sync`
(AirPlay receiver) only runs while the volume knob is on. Unlike
Bluetooth there's no separate "powered/discoverable" adapter state to
toggle — shairport-sync only advertises over mDNS and accepts connections
while its own process is running, so this agent's whole job is starting
and stopping `shairport-sync.service`. Stopping it both removes the
AirPlay listing from nearby devices' pickers and immediately drops any
active session — there's no graceful "just disconnect the client"
command in shairport-sync, so a stop (or restart, for the arbitration
case below) is also how a lost arbitration round gets enforced.

`shairport-sync` detects its own "actually playing" moment (needed for
the arbitration below) via its `run_this_before_play_begins`/
`run_this_after_play_ends` hooks in `/etc/shairport-sync.conf`
(device-only, not tracked in this repo) — but that config runs as
shairport-sync's own unprivileged user, which has no access to the MQTT
credentials it needs to actually publish anything. See
[`airplay-notify.sh`](airplay-notify.sh)'s own header comment for the
narrow `sudo` bridge that solves this (`/etc/sudoers.d/philco-airplay`,
device-only, grants exactly two argument-pinned invocations of that
script — nothing broader).

## Source arbitration

Spotify, Bluetooth, and AirPlay share one ALSA output — only one can
actually be producing sound at a time — and "last one to start wins":
- A phone starting playback over Bluetooth, or a device connecting and
  playing over AirPlay, pauses whatever Spotify station/static was
  playing.
- Turning the station dial to a different station takes the speaker back
  from Bluetooth (sends an actual AVRCP pause to the phone) or AirPlay
  (restarts `shairport-sync`, dropping the session).
- Bluetooth and AirPlay also take over from *each other* the same way.

This is `station-agent.py`/`bluetooth-agent.py`/`airplay-agent.py` all
talking over the same small set of MQTT topics
(`philco/audio/<source>/active` — each agent publishes on its own topic
the instant it starts playing, and subscribes to the other two, pausing/
stopping itself on either). A source going quiet on its own never
automatically resumes another; only an actual new action (dial move,
phone connecting) does.

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
sudo amixer -D eq cset numid=4 40,40   # numid=4 is the 250 Hz band -- see below on why sudo matters here
```
Changes made this way aren't reflected on the touchscreen and won't
survive a reboot — use the touchscreen (or publish to
`philco/eq/set/<band>` over MQTT) for anything that should stick.

Controls are `numid=1..10`, one per band in order 31 Hz, 63 Hz, 125 Hz,
250 Hz, 500 Hz, 1 kHz, 2 kHz, 4 kHz, 8 kHz, 16 kHz. Range is **0-100, not
dB** — 66 is flat/0dB.

**Gotcha worth knowing before debugging "the EQ isn't doing anything":**
`alsaequal` (the LADSPA plugin behind the `eq` ALSA device) keeps its
live band-gain values in a file at `$HOME/.alsaequal.bin` — **per-user,
not a single system-wide store.** A command run as a different effective
user (or the same user without `sudo`, since that changes `$HOME`) reads
or writes a *different* copy of the EQ state and will silently look like
it did nothing to actual playback, even though `amixer` reports success.
Every real audio process on this Pi (`go-librespot`, `sox`,
`bluealsa-aplay`, `shairport-sync`, `eq-agent.service`) is deliberately
configured to resolve `$HOME=/root` (either running as root directly, or
— for the two that run as their own unprivileged user —
`Environment=HOME=/root` plus a narrow ACL granting that user `rw` on
`/root/.alsaequal.bin` specifically). So: always `sudo` when checking or
setting EQ values by hand, or you'll be reading/writing a phantom copy
nothing else ever sees.

## MQTT

Every agent on this Pi (`station-agent.py`, `bluetooth-agent.py`,
`airplay-agent.py`, `eq-agent.py`, `spotify-volume-agent.py`) talks to
the same Mosquitto broker (the Home Assistant add-on), for both
control-topic input from `philco-ui` and the source-arbitration topics
above. Broker host/port/credentials live in `/etc/philco-mqtt/.env`
(mode `600`) — a matching file exists on `philco-ui` with its own scoped
login; each Pi has its own narrow, single-purpose Mosquitto login rather
than a shared one, so either can be revoked independently.

To test connectivity by hand without printing the credentials to a
terminal history:
```
sudo apt-get install -y mosquitto-clients   # one-time
sudo bash -c 'set -a; source /etc/philco-mqtt/.env; set +a; mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" -t test -m ping -d'
```
The `CONNACK` code in the debug output is the clearest signal: `0` =
success, `5` = not authorized. Home Assistant add-ons (including
Mosquitto) need an explicit restart to pick up a config change like a new
login — easy to forget, and looks identical to "wrong password" from the
client side.

## How we confirmed this isn't a prebuilt image

- `/etc/rpi-issue` and `/etc/os-release` both identify it as plain
  Raspberry Pi OS — a dedicated distro (moOde, Volumio, RuneAudio,
  HiFiBerryOS, etc.) would report its own OS name here instead.
- `/etc/apt/sources.list.d/` has only the official Raspberry Pi repo and
  any add-on package repos actually in use — no third-party image-vendor
  repo.
- `dpkg.log` timestamps for `go-librespot`/`shairport-sync`/etc. don't
  match the OS image's own build date, and are spread across separate
  install sessions rather than landing in one two-minute window. If this
  were a single prebuilt image, those packages would carry the same build
  timestamp as the OS itself. Instead, someone flashed plain Raspberry Pi
  OS and installed each piece manually, separately, over time — not one
  appliance flash. (Easy to misremember as prebuilt — some of these
  installers are a single curl-pipe-bash command that feels like flashing
  an appliance.)

## Current health

Has **not** yet had the journald size cap / disk-space watchdog from
[scripts/pi-maintenance/](../scripts/pi-maintenance/) applied — the same
failure mode that hit `philco-ui` (unbounded journal growth over a year+
of unattended uptime eating the whole card) could hit this box too given
enough time. Worth applying the same guardrails here preemptively rather
than waiting for it to happen again.

## Remote access

Same toggleable `claude-agent` SSH account as the UI Pi — see
[scripts/remote-access/](../scripts/remote-access/). Same keypair is
trusted on both machines; revocation is per-device via each Pi's own
`agent-access-off.sh`, so sharing the key doesn't reduce isolation
between the two boxes.
