import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './StudioLight.css'
import StudioApp from './StudioApp.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <StudioApp />
  </StrictMode>,
)
