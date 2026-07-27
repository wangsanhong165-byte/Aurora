import { electronWindowBridge } from '../session/electron-window-bridge'

declare global {
  interface Window {
    electronAPI?: {
      platform: string
      minimize: () => void
      close: () => void
      setAlwaysOnTop: (value: boolean) => void
      setPetMode: (enabled: boolean) => void
      getSettings: () => Record<string, unknown>
      getStatus?: () => Promise<{ services?: Array<Record<string, unknown>> }>
    }
  }
}

export function TitleBar() {
  const api = electronWindowBridge

  return (
    <header className="title-bar" aria-label="窗口控制区">
      <span className="title-bar-drag-region" aria-hidden="true" />
      <div className="window-controls">
        {api && (
          <>
            <button type="button" onClick={() => api.minimize()} aria-label="最小化">最小化</button>
            <button type="button" className="window-close" onClick={() => api.close()} aria-label="关闭">关闭</button>
          </>
        )}
      </div>
    </header>
  )
}
