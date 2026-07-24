import { createRoot, type Container } from 'react-dom/client'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element not found')

// Dynamic import to make the App the main chunk
async function main() {
  const { default: App } = await import('./App')
  createRoot(rootEl as Container).render(<App />)
}

main()
