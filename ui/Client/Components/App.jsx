import faceplate from '../Assets/faceplate.png'
import pointer from '../Assets/pointer.png'
import { w3cwebsocket } from 'websocket'
import React from 'react'

class App extends React.Component {
  static updateAmount = 1
  state = {
    rotation: 0,
    mode: null,
    eq: {},
    systemStatus: {}
  }
  getPointerRef = el => {
    this.pointer = el
  }
  radioUpdater = val => {
    this.setState({ rotation: (this.state.rotation + val) % 360 })
  }
  sendEqSet = (band, gain) => {
    if (this.client && this.client.readyState === this.client.OPEN) {
      this.client.send(JSON.stringify({ eqSet: { band, gain } }))
    }
  }
  sendSystemRestart = service => {
    if (this.client && this.client.readyState === this.client.OPEN) {
      this.client.send(JSON.stringify({ systemRestart: service }))
    }
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
          if (socketData.mode !== undefined) {
            this.setState({ mode: socketData.mode })
          }
          if (socketData.eq) {
            this.setState({ eq: socketData.eq })
          }
          if (socketData.systemStatus) {
            this.setState({ systemStatus: socketData.systemStatus })
          }
        } catch (e) {}
      } else {
        console.log(typeof e.data)
      }
    }
  }
  render() {
    if (this.state.mode === 6) {
      return <EqMixerScreen eq={this.state.eq} onChange={this.sendEqSet} />
    }

    if (this.state.mode === 5) {
      return <SystemStatusScreen status={this.state.systemStatus} onRestart={this.sendSystemRestart} />
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

// Subset of eq-agent.py's full 10-band BAND_NUMID set on the radio Pi --
// 6 sliders is more usable on an 800px touchscreen than all 10, weighted
// toward the 125-1k range where the muddy-midrange problem actually
// lives. The radio Pi still has full 10-band control via `alsamixer -D
// eq`; this is just which bands the touchscreen exposes.
const EQ_BANDS = ['63', '125', '250', '500', '1k', '4k']
const EQ_MIN = 0
const EQ_MAX = 100
const EQ_FLAT = 66

class EqMixerScreen extends React.Component {
  state = { savedEq: null }
  toggleFlat = () => {
    if (this.state.savedEq === null) {
      // Switching to flat: remember the current settings so the button
      // can restore them, then push flat to every band for an A/B
      // comparison against how it sounded before.
      this.setState({ savedEq: { ...this.props.eq } })
      EQ_BANDS.forEach(band => this.props.onChange(band, EQ_FLAT))
    } else {
      const saved = this.state.savedEq
      EQ_BANDS.forEach(band => {
        const gain = saved[band] !== undefined ? Number(saved[band]) : EQ_FLAT
        this.props.onChange(band, gain)
      })
      this.setState({ savedEq: null })
    }
  }
  render() {
    return (
      <div className="eq-screen">
        <div className="eq-title">Equalizer</div>
        <div className="eq-bands">
          {EQ_BANDS.map(band => (
            <EqBandSlider
              key={band}
              band={band}
              gain={this.props.eq[band] !== undefined ? Number(this.props.eq[band]) : EQ_FLAT}
              onChange={this.props.onChange}
            />
          ))}
        </div>
        <div
          className={`eq-flat-toggle${this.state.savedEq !== null ? ' active' : ''}`}
          onClick={this.toggleFlat}
        >
          {this.state.savedEq !== null ? 'Restore' : 'Flat (A/B)'}
        </div>
      </div>
    )
  }
}

const DOUBLE_TAP_MS = 350

class EqBandSlider extends React.Component {
  debounceTimer = null
  lastTapAt = 0
  state = { gain: this.props.gain }
  componentDidUpdate(prevProps) {
    // Only accept a server-driven update when the user isn't mid-drag --
    // otherwise a retained-state echo could yank the slider out from
    // under a finger.
    if (prevProps.gain !== this.props.gain && this.debounceTimer === null) {
      this.setState({ gain: this.props.gain })
    }
  }
  handleChange = e => {
    const gain = Number(e.target.value)
    this.setState({ gain })
    clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null
      this.props.onChange(this.props.band, gain)
    }, 200)
  }
  handleTap = e => {
    // Touchscreens fire a touchend then a synthetic click for the same
    // physical tap -- suppress the synthetic one so a real double-tap
    // isn't miscounted as two taps from one touch.
    if (e.type === 'touchend') e.preventDefault()
    const now = Date.now()
    if (now - this.lastTapAt < DOUBLE_TAP_MS) {
      this.lastTapAt = 0
      clearTimeout(this.debounceTimer)
      this.debounceTimer = null
      this.setState({ gain: EQ_FLAT })
      this.props.onChange(this.props.band, EQ_FLAT)
    } else {
      this.lastTapAt = now
    }
  }
  render() {
    return (
      <div className="eq-band">
        <div className="eq-slider-wrap" onClick={this.handleTap} onTouchEnd={this.handleTap}>
          <input
            className="eq-slider"
            type="range"
            min={EQ_MIN}
            max={EQ_MAX}
            step="1"
            value={this.state.gain}
            onChange={this.handleChange}
          />
        </div>
        <div className="eq-band-label">{this.props.band}</div>
      </div>
    )
  }
}

// Mode-switch position 5: live health for the radio Pi's three audio
// sources (go-librespot/Bluetooth/AirPlay), with a per-source restart
// button -- see radio-pi/system-status-agent.py. Built after a real
// incident (2026-09) where go-librespot's Spotify auth silently wedged
// after ~37 days of uptime with no visible symptom short of an SSH
// session; this screen exists so that kind of thing can be checked and
// fixed from the cabinet itself.
const SYSTEM_STATUS_SERVICES = [
  { key: 'spotify', label: 'Spotify' },
  { key: 'bluetooth', label: 'Bluetooth' },
  { key: 'airplay', label: 'AirPlay' },
]

// How long a restart button stays disabled after a tap -- system-status-
// agent.py's own restart handling takes up to ~12s to settle on a final
// status (see RESTART_RECHECK_DELAYS_SECONDS there), so this just prevents
// impatient double-taps from firing several redundant restarts in a row.
const RESTART_DISABLE_MS = 5000

class SystemStatusRow extends React.Component {
  state = { restarting: false }
  handleRestart = () => {
    if (this.state.restarting) return
    this.props.onRestart(this.props.serviceKey)
    this.setState({ restarting: true })
    setTimeout(() => this.setState({ restarting: false }), RESTART_DISABLE_MS)
  }
  render() {
    const { label, status } = this.props
    const state = (status && status.state) || 'unknown'
    const detail = (status && status.detail) || 'no status yet'
    return (
      <div className="status-row">
        <div className={`status-indicator status-${state}`} />
        <div className="status-text">
          <div className="status-label">{label}</div>
          <div className="status-detail">{detail}</div>
        </div>
        <div
          className={`status-restart-btn${this.state.restarting ? ' disabled' : ''}`}
          onClick={this.handleRestart}
        >
          Restart
        </div>
      </div>
    )
  }
}

const SystemStatusScreen = props => {
  return (
    <div className="status-screen">
      <div className="status-title">System Status</div>
      {SYSTEM_STATUS_SERVICES.map(service => (
        <SystemStatusRow
          key={service.key}
          serviceKey={service.key}
          label={service.label}
          status={props.status[service.key]}
          onRestart={props.onRestart}
        />
      ))}
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
