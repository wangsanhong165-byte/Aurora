import { StoreProvider } from './core/store'
import { ErrorBoundary } from './ui/ErrorBoundary'
import { DesktopSessionWorkspace } from './session/DesktopSessionProvider'
import './styles/index.css'

export default function App() {
  return (
    <ErrorBoundary>
      <StoreProvider>
        <DesktopSessionWorkspace />
      </StoreProvider>
    </ErrorBoundary>
  )
}
