import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import WorkspaceView from './WorkspaceView.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceView />
  </StrictMode>,
)
