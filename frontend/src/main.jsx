import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import TaaSPlatform from './TaaSPlatform.jsx'
import './App.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <TaaSPlatform />
  </StrictMode>,
)
