import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { applyThemePreference, readThemePreference } from './lib/theme'
import { WebApplication } from './app/WebApplication'
import './styles.css'

applyThemePreference(readThemePreference())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <WebApplication publishableKey={import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? ''} />
  </StrictMode>,
)
