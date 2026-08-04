#!/usr/bin/env node
require('dotenv').config({ path: '/etc/philco-mqtt/.env' })
const WebSocketServer = require('websocket').server
const SerialPort = require('serialport')
const http = require('http')
const { createBridge } = require('./mqtt-bridge')

let connection = null

const mqttBridge = createBridge({
  host: process.env.MQTT_HOST,
  port: process.env.MQTT_PORT,
  username: process.env.MQTT_USERNAME,
  password: process.env.MQTT_PASSWORD,
  onEqUpdate: (eq) => {
    if (connection != null) {
      connection.sendUTF(JSON.stringify({ eq }))
    }
  },
})

// websocket server
const server = http.createServer((request, response) => {
  console.log(new Date() + ' Received request for ' + request.url)
  response.writeHead(404)
  response.end()
})
server.listen(8080, function() {
  console.log(new Date() + ' Server is listening on port 8080')
})
wsServer = new WebSocketServer({
  httpServer: server,
  autoAcceptConnections: false
})

// serial port
const port = new SerialPort('/dev/ttyACM0', {
  baudRate: 9600
})

wsServer.on('request', request => {
  // note: my server runs in a docker container without ports exposed so I dont worry
  // about unknown origins. If that isn't true for you, put some logic here to filter
  // out traffic from unknown origins.
  connection = request.accept('echo-protocol', request.origin)
  console.log(new Date() + ' Connection accepted.')

  connection.on('message', message => {
    if (message.type !== 'utf8') return
    try {
      const data = JSON.parse(message.utf8Data)
      if (data.eqSet) {
        mqttBridge.publishEqSet(data.eqSet.band, data.eqSet.gain)
      }
    } catch (e) {
      console.log(new Date() + ' Failed to parse websocket message: ' + e.message)
    }
  })

  connection.on('close', (reasonCode, description) => {
    console.log(
      new Date() + ' Peer ' + connection.remoteAddress + ' disconnected.'
    )
  })
})

// Maps the numeric control type the Arduino sends (see STATION/VOLUME/MULTI1
// in arduino/controls/controls.ino) to the mqtt-bridge control keys.
const CONTROL_TYPES = { 0: 'station', 1: 'volume', 2: 'multi1' }

// The station potentiometer is read with analogRead() on a Teensy 2.0
// (10-bit ADC, PIN_F0/PIN_B6-style AVR pin names in controls.ino). Unlike
// the volume knob, this pot does NOT span the full 0-1023 ADC range --
// confirmed via this file's own serial log across a full physical dial
// sweep: raw values only ever ranged ~12-574. Must match radio-pi/
// station-agent.py's own STATION_RAW_MIN/STATION_RAW_MAX, since both
// derive their sense of "how far around" from the same raw ADC value.
const STATION_RAW_MIN = 0
const STATION_RAW_MAX = 600

// Volume's own ADC range is close enough to the full 0-1023 (observed
// 14-984) that it isn't worth a similar correction.
const VOLUME_ADC_MAX = 1023

// Must match radio-pi/station-agent.py's own VOLUME_OFF_THRESHOLD -- both
// treat this same 0-100 scale the same way as "the knob's off click-stop".
const VOLUME_OFF_THRESHOLD = 2

let lastSpotifyVolume = null

// The mode switch's "3" position (multi1_2_pin / PIN_F5 in controls.ino)
// has a hardware fault -- that pin never reads LOW, so the Arduino always
// falls through to its "nothing pressed" default (0) at that position
// instead of sending 3. Confirmed repeatable, not intermittent. Remap the
// raw values (observed while rotating through all 6 positions in order:
// 6,5,4,0,2,1) to consecutive logical positions here rather than in the
// Arduino sketch, so it's easy to adjust without reflashing the Teensy.
// The real fix is checking that wire/connection; this is a workaround.
const MULTI1_REMAP = { 6: 1, 5: 2, 4: 3, 0: 4, 2: 5, 1: 6 }

let serialBuffer = ''

// Switches the port into "flowing mode"
port.on('data', function (data) {
  console.log('Data:', data)

  // the Arduino sends lines like "0,512" (type,value) -- buffer across
  // chunks since a single serial read isn't guaranteed to land on a line
  // boundary, then publish each complete line to MQTT and relay the
  // station value to the UI so its pointer can rotate.
  serialBuffer += data.toString()
  const lines = serialBuffer.split('\n')
  serialBuffer = lines.pop()
  lines.forEach((line) => {
    const [type, value] = line.trim().split(',')
    const key = CONTROL_TYPES[type]
    if (!key || value === undefined) return

    const publishedValue = key === 'multi1' ? MULTI1_REMAP[value] : value
    if (publishedValue === undefined) return

    // While the radio is off, station/mode changes are ignored entirely --
    // not even published to MQTT -- so nothing downstream (station-agent.py,
    // the touchscreen's EQ-mixer mode screen, HA sensors) reacts to moving
    // the dial/switch while off. Also closes a real gap found in station-
    // agent.py: without this, moving the dial while off could still start
    // playback, since station-agent had no way to know the radio was off.
    // `lastSpotifyVolume === null` (volume state not known yet) does NOT
    // suppress -- fail open rather than silently withhold updates forever
    // if a station/mode message happens to arrive before the first volume
    // reading.
    const radioIsOff = lastSpotifyVolume !== null && lastSpotifyVolume <= VOLUME_OFF_THRESHOLD
    if (radioIsOff && (key === 'station' || key === 'multi1')) return

    mqttBridge.publish(key, publishedValue)

    if (key === 'station' && connection != null) {
      const clamped = Math.max(STATION_RAW_MIN, Math.min(STATION_RAW_MAX, Number(value)))
      const radioSetting = Math.round(((clamped - STATION_RAW_MIN) / (STATION_RAW_MAX - STATION_RAW_MIN)) * 360)
      connection.sendUTF(JSON.stringify({ radioSetting }))
    }

    if (key === 'multi1' && connection != null) {
      connection.sendUTF(JSON.stringify({ mode: Number(publishedValue) }))
    }

    if (key === 'volume') {
      const spotifyVolume = Math.round((Number(value) / VOLUME_ADC_MAX) * 100)
      mqttBridge.publishSpotifyVolumeSet(spotifyVolume)

      const wasOff = lastSpotifyVolume !== null && lastSpotifyVolume <= VOLUME_OFF_THRESHOLD
      const isNowOn = spotifyVolume > VOLUME_OFF_THRESHOLD
      if (wasOff && isNowOn) {
        mqttBridge.publishStationReassert()
      }
      lastSpotifyVolume = spotifyVolume
    }
  })
})
