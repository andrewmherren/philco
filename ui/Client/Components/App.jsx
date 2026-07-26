import faceplate from '../Assets/faceplate.png'
import pointer from '../Assets/pointer.png'
import { w3cwebsocket } from 'websocket'
import React from 'react'

class App extends React.Component {
  static updateAmount = 1
  state = {
    rotation: 0,
    pairingCode: '',
    pairingState: 'idle'
  }
  getPointerRef = el => {
    this.pointer = el
  }
  radioUpdater = val => {
    this.setState({ rotation: (this.state.rotation + val) % 360 })
  }
  sendPairingResponse = response => {
    if (this.client && this.client.readyState === this.client.OPEN) {
      this.client.send(JSON.stringify({ pairingResponse: response }))
    }
    // Return to the main screen immediately on button press rather than
    // waiting for the radio Pi's agent to resolve and publish 'idle' back --
    // the user's part is done as soon as they've tapped Pair/Cancel.
    this.setState({ pairingState: 'idle', pairingCode: '' })
  }
  componentDidMount() {
    const client = new w3cwebsocket('ws://localhost:8080/', 'echo-protocol')
    this.client = client
    client.onerror = () => {
      console.log('Connection Error')
    }
    client.onopen = () => {
      console.log('WebSocket Client Connected')
    }
    client.onclose = () => {
      console.log('echo-protocol Client Closed')
    }
    client.onmessage = e => {
      if (typeof e.data === 'string') {
        try {
          const socketData = JSON.parse(e.data)
          if (socketData.radioSetting) {
            this.setState({ rotation: socketData.radioSetting })
          }
          if (socketData.pairing) {
            this.setState({
              pairingCode: socketData.pairing.code,
              pairingState: socketData.pairing.state
            })
          }
        } catch (e) {}
      } else {
        console.log(typeof e.data)
      }
    }
  }
  render() {
    if (this.state.pairingState === 'active' && this.state.pairingCode) {
      return (
        <PairingScreen
          code={this.state.pairingCode}
          onPair={() => this.sendPairingResponse('confirm')}
          onCancel={() => this.sendPairingResponse('deny')}
        />
      )
    }

    if (this.pointer) {
      this.pointer.style.transform = `rotate(${this.state.rotation}deg)`
    }
    return (
      <React.Fragment>
        <MenuOutside
          leftButtonHandler={() => this.radioUpdater(App.updateAmount * -1)}
          centerButtonHandler={() => alert('top center button')}
          rightButtonHandler={() => this.radioUpdater(App.updateAmount * 1)}
        />
        <MenuInside1
          leftButtonHandler={() => alert('top middle left button')}
          rightButtonHandler={() => alert('top middle right buton')}
        />
        <MenuInside2
          leftButtonHandler={() => alert('bottom middle left button')}
          rightButtonHandler={() => alert('bottom middle right buton')}
        />
        <MenuOutside
          leftButtonHandler={() => alert('bottom left button')}
          centerButtonHandler={() => alert('bottom center button')}
          rightButtonHandler={() => alert('bottom right buton')}
        />
        <img id="faceplate" src={faceplate} />
        <img ref={this.getPointerRef} id="pointer" src={pointer} />
      </React.Fragment>
    )
  }
}

export default App

const PairingScreen = props => {
  return (
    <div className="pairing-screen">
      <div className="pairing-code">{props.code}</div>
      <div className="pairing-label">
        Confirm this code matches your phone to pair
      </div>
      <div className="pairing-buttons">
        <div className="pairing-button pair" onClick={props.onPair}>
          Pair
        </div>
        <div className="pairing-button cancel" onClick={props.onCancel}>
          Cancel
        </div>
      </div>
    </div>
  )
}

const MenuOutside = props => {
  return (
    <div className="menu top">
      <div className="button" onClick={props.leftButtonHandler} />
      <div className="button" onClick={props.centerButtonHandler} />
      <div className="button" onClick={props.rightButtonHandler} />
    </div>
  )
}

const MenuInside1 = props => {
  return (
    <div className="menu middle1">
      <div className="button" onClick={props.leftButtonHandler} />
      <div className="dial" />
      <div className="button" onClick={props.rightButtonHandler} />
    </div>
  )
}

const MenuInside2 = props => {
  return (
    <div className="menu middle2">
      <div className="button" onClick={props.leftButtonHandler} />
      <div className="dial" />
      <div className="button" onClick={props.rightButtonHandler} />
    </div>
  )
}
