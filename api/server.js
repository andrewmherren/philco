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
  onPairingUpdate: (pairing) => {
    if (connection != null) {
      connection.sendUTF(JSON.stringify({ pairing }))
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
      if (data.pairingResponse) {
        mqttBridge.respondToPairing(data.pairingResponse)
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

// serial controller
// const sendSetting = connection => {
//   radioSetting = (radioSetting + 1) % 360
//   connection.sendUTF(JSON.stringify({ radioSetting }))
// }


// port.write('main screen turn on', function(err) {
//   if (err) {
//     return console.log('Error on write: ', err.message)
//   }
//   console.log('message written')
// })

// Read data that is available but keep the stream in "paused mode"
// port.on('readable', function () {
//   console.log('Data:', port.read())
// })

// Maps the numeric control type the Arduino sends (see STATION/VOLUME/MULTI1
// in arduino/controls/controls.ino) to the mqtt-bridge control keys.
const CONTROL_TYPES = { 0: 'station', 1: 'volume', 2: 'multi1' }

let serialBuffer = ''

// Switches the port into "flowing mode"
port.on('data', function (data) {
  console.log('Data:', data)
  if(connection != null) {
    // send the serial data across the websocket
    connection.sendUTF(data)
  }

  // the Arduino sends lines like "0,512" (type,value) -- buffer across
  // chunks since a single serial read isn't guaranteed to land on a line
  // boundary, then publish each complete line to MQTT.
  serialBuffer += data.toString()
  const lines = serialBuffer.split('\n')
  serialBuffer = lines.pop()
  lines.forEach((line) => {
    const [type, value] = line.trim().split(',')
    const key = CONTROL_TYPES[type]
    if (key && value !== undefined) {
      mqttBridge.publish(key, value)
    }
  })
})
