import React from 'react'
import faceplate from '../Assets/faceplate2.png'
import pointer from '../Assets/pointer2.png'

class App extends React.Component {
  static updateAmount = 1
  state = {
    rotation: 0
  }
  getPointerRef = el => {
    this.pointer = el
  }
  radioUpdater = val => {
    this.setState({ rotation: (this.state.rotation + val) % 360 })
  }
  render() {
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
