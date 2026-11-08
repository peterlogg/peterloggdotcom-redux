import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// /admin is a separate lazy bundle so the public site never loads Firebase.
// If its file is gone (a deploy happened while this page was open), reload once to pick up the new build.
const RELOADED = 'aker-admin-reloaded'
const Admin = lazy(() =>
  import('./admin/Admin.tsx')
    .then((m) => {
      try { sessionStorage.removeItem(RELOADED) } catch { /* ignore */ }
      return m
    })
    .catch((err) => {
      let reloaded = false
      try { reloaded = sessionStorage.getItem(RELOADED) === '1'; sessionStorage.setItem(RELOADED, '1') } catch { /* ignore */ }
      if (!reloaded) window.location.reload()
      throw err
    }),
)
const isAdmin = window.location.pathname.startsWith('/admin')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isAdmin ? (
      <Suspense fallback={<main className="page"><p className="muted">Loading admin…</p></main>}>
        <Admin />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
