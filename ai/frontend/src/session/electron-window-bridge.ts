declare global {
  interface Window {
    electronAPI?: {
      platform: string
      minimize: () => void
      maximize: () => Promise<boolean> | boolean
      isMaximized: () => Promise<boolean> | boolean
      close: () => void
      setAlwaysOnTop: (value: boolean) => void
      setPetMode: (enabled: boolean) => void
      getSettings: () => Record<string, unknown>
      getStatus?: () => Promise<{ services?: Array<Record<string, unknown>> }>
    }
  }
}

export class ElectronWindowBridge {
  get available(): boolean {
    return typeof window !== 'undefined' && Boolean(window.electronAPI)
  }

  minimize() { return window.electronAPI?.minimize?.() }
  maximize() { return window.electronAPI?.maximize?.() }
  isMaximized() { return window.electronAPI?.isMaximized?.() }
  close() { return window.electronAPI?.close?.() }
  setAlwaysOnTop(value: boolean) { return window.electronAPI?.setAlwaysOnTop?.(value) }
  setPetMode(value: boolean) { return window.electronAPI?.setPetMode?.(value) }
  getStatus() {
    return window.electronAPI?.getStatus?.() ?? Promise.resolve({ ready: false, services: [] })
  }
}

export const electronWindowBridge = new ElectronWindowBridge()
