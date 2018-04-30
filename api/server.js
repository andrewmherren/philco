#!/usr/bin/env node
const WebSocketServer = require('websocket').server
const http = require('http')

let radioSetting = 0
let timer = null

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

wsServer.on('request', request => {
  // note: my server runs in a docker container without ports exposed so I dont worry
  // about unknown origins. If that isn't true for you, put some logic here to filter
  // out traffic from unknown origins.
  const connection = request.accept('echo-protocol', request.origin)
  console.log(new Date() + ' Connection accepted.')

  if (timer == null) {
    timer = setInterval(() => sendSetting(connection), 100)
    radioSetting = 0
  } else {
    console.log(timer)
  }

  connection.on('close', (reasonCode, description) => {
    if (timer != null) {
      clearInterval(timer)
      timer = null
    }
    console.log(
      new Date() + ' Peer ' + connection.remoteAddress + ' disconnected.'
    )
  })
})

const sendSetting = connection => {
  radioSetting = (radioSetting + 1) % 360
  connection.sendUTF(JSON.stringify({ radioSetting }))
}
