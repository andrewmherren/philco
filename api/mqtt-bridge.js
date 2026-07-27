#!/usr/bin/env node
// Publishes physical control values (from the Arduino, via server.js) to
// MQTT so Home Assistant can react to them -- e.g. trigger a scene when
// the mode switch lands on a given position. Publishes Home Assistant MQTT
// Discovery config once on connect so these show up as entities with no
// manual YAML.

const mqtt = require('mqtt')

const TOPIC_PREFIX = 'philco/ui/controls'
const DISCOVERY_PREFIX = 'homeassistant'
const PAIRING_CODE_TOPIC = 'philco/pairing/code'
const PAIRING_STATE_TOPIC = 'philco/pairing/state'
const PAIRING_RESPONSE_TOPIC = 'philco/pairing/response'

// The radio Pi's eq-agent.py owns these -- band keys match its
// BAND_NUMID keys (ISO-ish labels for the alsaequal 10-band graphic EQ).
// Payloads are the plugin's native 0-100 scale (66 = flat), not dB.
const EQ_SET_TOPIC_PREFIX = 'philco/eq/set'
const EQ_STATE_TOPIC_PREFIX = 'philco/eq/state'

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

function createBridge({ host, port, username, password, onPairingUpdate, onEqUpdate }) {
  if (!host) {
    console.log(new Date() + ' MQTT bridge disabled: no host configured')
    return { publish() {}, respondToPairing() {}, publishEqSet() {} }
  }

  const client = mqtt.connect(`mqtt://${host}:${port || 1883}`, {
    username,
    password,
    clientId: `philco-ui-bridge-${Math.random().toString(16).slice(2, 8)}`,
    reconnectPeriod: 5000,
  })

  // philco (the radio Pi)'s bt-agent publishes the current Bluetooth
  // pairing passkey here -- this Pi has the only screen, so it's
  // responsible for displaying it. See radio-pi/bt-agent.py.
  const pairing = { code: '', state: 'idle' }
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
      [PAIRING_CODE_TOPIC, PAIRING_STATE_TOPIC, `${EQ_STATE_TOPIC_PREFIX}/+`],
      (err) => {
        if (err) console.log(new Date() + ' MQTT subscribe error: ' + err.message)
      }
    )
  })

  client.on('message', (topic, message) => {
    if (topic === PAIRING_CODE_TOPIC) {
      pairing.code = message.toString()
      if (onPairingUpdate) onPairingUpdate({ ...pairing })
    } else if (topic === PAIRING_STATE_TOPIC) {
      pairing.state = message.toString()
      if (onPairingUpdate) onPairingUpdate({ ...pairing })
    } else if (topic.startsWith(`${EQ_STATE_TOPIC_PREFIX}/`)) {
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
      client.publish(`${TOPIC_PREFIX}/${key}`, String(value))
    },
    respondToPairing(response) {
      if (!client.connected) return
      client.publish(PAIRING_RESPONSE_TOPIC, response)
    },
    publishEqSet(band, gain) {
      if (!client.connected) return
      client.publish(`${EQ_SET_TOPIC_PREFIX}/${band}`, String(gain))
    },
  }
}

module.exports = { createBridge }
