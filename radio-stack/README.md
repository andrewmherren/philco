## Project plan: a consistent radio stack across devices

Plan for the `revamp` branch: one consistent audio/Spotify/Home Assistant
stack that works the same way across every philco-style radio device,
whether it's a single Pi with local speakers or a split UI Pi + speaker Pi
pair (like the current `philco-ui` + `philco` devices — see
[radio-pi/README.md](../radio-pi/README.md)).

## Requirements

- Spotify Connect required.
- Home Assistant: a scene should be able to turn a radio on and play a
  specific Spotify playlist.
- Physical knobs/buttons/switches should drive the audio stack
  consistently, regardless of which Pi they're wired to.
- Free — no paid tiers or subscriptions.

## Decision: compose from proven free components, not a monolithic distro

Evaluated moOde, Volumio, HiFiBerryOS, balenaSound, and Berryaudio against
these requirements — none were a good foundation (paid Spotify tier,
reliability reports, cloud dependency, or too early-stage/undocumented
for our own hardware integration, respectively). Instead: three decoupled
layers, so the same recipe works on any device shape —

1. **Audio backend** (whichever Pi has the speakers): `go-librespot`,
   plus a hardware volume ceiling. This is what's running on the radio Pi
   today.
2. **Control bridge** (whichever Pi has the physical controls): the
   existing Arduino serial→websocket relay in this repo (`api/server.js`),
   extended to also publish to MQTT.
3. **Orchestration**: Home Assistant's native Spotify integration for the
   scene/playlist requirement, plus MQTT for physical-control-triggered
   automations.

## Status

- [x] Audio backend standardized on the radio Pi (`go-librespot`),
      including a hardware volume cap
- [x] Control bridge: `philco-ui`'s Arduino controls now publish to MQTT
- [x] Home Assistant's Spotify integration confirmed working end-to-end
- [x] Confirmed Home Assistant install type (Home Assistant OS)
- [x] Bluetooth and AirPlay added as additional volume-gated audio
      sources on the radio Pi, arbitrated against Spotify/static for the
      shared output — see [radio-pi/README.md](../radio-pi/README.md)
      (beyond the original Spotify-Connect-only requirement above, but
      built on the same audio-backend layer)
- [ ] Music Assistant add-on (for the broader multiroom/unification goal
      — not required for the core scene/playlist requirement)
- [ ] Wire Home Assistant scenes/automations to the control-bridge MQTT
      topics
- [ ] Apply this same recipe as the template for the next device

## More detail

Full reasoning for each decision lives in
[radio-pi/README.md](../radio-pi/README.md) and the main
[README.md](../README.md) — this file stays a quick, current-status
reference.
