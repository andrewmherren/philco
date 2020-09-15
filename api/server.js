#!/usr/bin/env node
const WebSocketServer = require('websocket').server
const SerialPort = require('serialport')
const http = require('http')

let connection = null

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
const port = new SerialPort('/dev/tty-usbserial1', {
  baudRate: 57600
})

wsServer.on('request', request => {
  // note: my server runs in a docker container without ports exposed so I dont worry
  // about unknown origins. If that isn't true for you, put some logic here to filter
  // out traffic from unknown origins.
  connection = request.accept('echo-protocol', request.origin)
  console.log(new Date() + ' Connection accepted.')

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

// Switches the port into "flowing mode"
port.on('data', function (data) {
  console.log('Data:', data)
  if(connection != null) {
    // send the serial data across the websocket
    connection.sendUTF(data)
  }
})
