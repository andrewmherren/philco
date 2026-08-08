import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './Components/App.jsx'

// Import css and fonts
require('./Styles/index.styl')

createRoot(document.getElementById('content')).render(<App />)
