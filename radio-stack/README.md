## Project plan: a consistent radio stack across devices

Plan for the `revamp` branch: one consistent audio/Bluetooth/Spotify/Home
Assistant stack that works the same way across every philco-style radio
device, whether it's a single Pi with local speakers or a split UI Pi +
speaker Pi pair (like the current `philco-ui` + `philco` devices — see
[radio-pi/README.md](../radio-pi/README.md)).

## Requirements

- Bluetooth (A2DP) and Spotify Connect required; AirPlay is a bonus.
- Security: no one but someone physically at the radio should be able to
  pair a new Bluetooth device (apartment building — no opportunistic
  neighbor pairing).
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

1. **Audio backend** (whichever Pi has the speakers): `go-librespot` +
   `shairport-sync` + BlueZ/PipeWire Bluetooth, plus a hardware volume
   ceiling. This is what's running on the radio Pi today.
2. **Control bridge** (whichever Pi has the physical controls): the
   existing Arduino serial→websocket relay in this repo (`api/server.js`),
   extended to also publish to MQTT.
3. **Orchestration**: Home Assistant's native Spotify integration for the
   scene/playlist requirement, plus MQTT for physical-control-triggered
   automations.

A hard limit worth knowing: plain Bluetooth audio (a phone streaming to
the speaker) is phone-initiated by the Bluetooth spec itself — no stack
lets Home Assistant "push" audio to a Bluetooth-paired phone. HA-triggered
playback only works through Spotify Connect or AirPlay.

## Status

- [x] Audio backend standardized on the radio Pi (`go-librespot` +
      `shairport-sync` + Bluetooth), including a hardware volume cap
- [x] Bluetooth pairing hardened — always discoverable, but pairing
      requires confirming a code on `philco-ui`'s touchscreen
- [x] Control bridge: `philco-ui`'s Arduino controls now publish to MQTT
- [x] Home Assistant's Spotify integration confirmed working end-to-end
- [x] Confirmed Home Assistant install type (Home Assistant OS)
- [ ] Bluetooth audio doesn't actually route to the speaker yet after
      pairing — open issue, not yet root-caused
- [ ] Music Assistant add-on (for the broader multiroom/unification goal
      — not required for the core scene/playlist requirement)
- [ ] Wire Home Assistant scenes/automations to the control-bridge MQTT
      topics
- [ ] Apply this same recipe as the template for the next device

## More detail

Full reasoning for each decision, debugging history, gotchas, and
detailed open-issue notes live in
[AGENT_SCRATCHPAD.md](../AGENT_SCRATCHPAD.md) at the repo root, not here
— this file stays a quick, current-status reference.
