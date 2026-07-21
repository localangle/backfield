/**
 * Playground is a single-route SPA (no React Router). Unknown paths still
 * serve index.html; this screen handles those client-side.
 */
export default function NotFound() {
  return (
    <div className="app-frame">
      <main className="not-found-page">
        <p className="not-found-code">404</p>
        <h1>Page not found</h1>
        <p>
          This page doesn’t exist or may have moved. Check the address, or go back to the API
          Playground.
        </p>
        <a className="connect-button" href="/">
          Back to API Playground
        </a>
      </main>
    </div>
  )
}
