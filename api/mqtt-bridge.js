#!/usr/bin/env node
// Publishes physical control values (from the Arduino, via server.js) to
// MQTT so Home Assistant can react to them -- e.g. trigger a scene when
// the mode switch lands on a given position. Publishes Home Assistant MQTT
// Discovery config once on connect so these show up as entities with no
// manual YAML.

const mqtt = require('mqtt')

const TOPIC_PREFIX = 'philco/ui/controls'
const DISCOVERY_PREFIX = 'homeassistant'

// The radio Pi's eq-agent.py owns these -- band keys match its
// BAND_NUMID keys (ISO-ish labels for the alsaequal 10-band graphic EQ).
// Payloads are the plugin's native 0-100 scale (66 = flat), not dB.
const EQ_SET_TOPIC_PREFIX = 'philco/eq/set'
const EQ_STATE_TOPIC_PREFIX = 'philco/eq/state'

// The radio Pi's spotify-volume-agent.py owns this -- knob-driven volume
// changes only, forwarded straight to go-librespot's own volume (0-100).
// Changes from the Spotify app itself reach go-librespot directly via
// the Connect protocol, no bridging needed for that direction.
const SPOTIFY_VOLUME_SET_TOPIC = 'philco/spotify/volume/set'

// radio-pi/station-agent.py owns this -- fired when volume crosses from
// off to on, so it re-applies whatever region is/should be current even
// though the dial itself hasn't moved (a plain station-topic republish
// doesn't work for this: same region index == station-agent's own
// no-op check, so it needs an explicit "please re-apply now" signal).
const STATION_REASSERT_TOPIC = 'philco/station/reassert'

const DEVICE = {
  identifiers: ['philco-ui-controls'],
  name: 'Philco UI Controls',
  manufacturer: 'philco (DIY)',
  model: 'Arduino control bridge',
}

const CONTROLS = {
  station: { name: 'Station Dial', icon: 'mdi:radio-tuner' },
  volume: { name: 'Volume Knob', icon: 'mdi:volume-high' },
  multi1: { name: 'Mode Switch', icon: 'mdi:tune-variant' },
}

function createBridge({ host, port, username, password, onEqUpdate }) {
  if (!host) {
    console.log(new Date() + ' MQTT bridge disabled: no host configured')
    return {
      publish() {},
      publishEqSet() {},
      publishSpotifyVolumeSet() {},
      publishStationReassert() {},
    }
  }

  const client = mqtt.connect(`mqtt://${host}:${port || 1883}`, {
    username,
    password,
    clientId: `philco-ui-bridge-${Math.random().toString(16).slice(2, 8)}`,
    reconnectPeriod: 5000,
  })

  const eq = {}

  client.on('connect', () => {
    console.log(new Date() + ' MQTT connected, publishing discovery config')
    Object.entries(CONTROLS).forEach(([key, meta]) => {
      client.publish(
        `${DISCOVERY_PREFIX}/sensor/philco_ui_${key}/config`,
        JSON.stringify({
          name: meta.name,
          icon: meta.icon,
          state_topic: `${TOPIC_PREFIX}/${key}`,
          unique_id: `philco_ui_${key}`,
          device: DEVICE,
        }),
        { retain: true }
      )
    })
    client.subscribe(
      [`${EQ_STATE_TOPIC_PREFIX}/+`],
      (err) => {
        if (err) console.log(new Date() + ' MQTT subscribe error: ' + err.message)
      }
    )
  })

  client.on('message', (topic, message) => {
    if (topic.startsWith(`${EQ_STATE_TOPIC_PREFIX}/`)) {
      const band = topic.slice(EQ_STATE_TOPIC_PREFIX.length + 1)
      eq[band] = message.toString()
      if (onEqUpdate) onEqUpdate({ ...eq })
    }
  })

  client.on('error', (err) => {
    console.log(new Date() + ' MQTT error: ' + err.message)
  })

  return {
    publish(key, value) {
      if (!CONTROLS[key] || !client.connected) return
      // Retained so a fresh subscriber (e.g. a radio-Pi daemon restarting)
      // can learn the physical control's last-known position immediately,
      // instead of only finding out the next time it moves.
      client.publish(`${TOPIC_PREFIX}/${key}`, String(value), { retain: true })
    },
    publishEqSet(band, gain) {
      if (!client.connected) return
      client.publish(`${EQ_SET_TOPIC_PREFIX}/${band}`, String(gain))
    },
    publishSpotifyVolumeSet(volume) {
      if (!client.connected) return
      client.publish(SPOTIFY_VOLUME_SET_TOPIC, String(volume))
    },
    publishStationReassert() {
      if (!client.connected) return
      client.publish(STATION_REASSERT_TOPIC, '1')
    },
  }
}

module.exports = { createBridge }
