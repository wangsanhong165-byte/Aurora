export class ElectronWindowBridge {
  get available(): boolean {
    return typeof window !== 'undefined' && Boolean(window.electronAPI)
  }

  minimize() { return window.electronAPI?.minimize?.() }
  close() { return window.electronAPI?.close?.() }
  setAlwaysOnTop(value: boolean) { return window.electronAPI?.setAlwaysOnTop?.(value) }
  setPetMode(value: boolean) { return window.electronAPI?.setPetMode?.(value) }
  getStatus() {
    return window.electronAPI?.getStatus?.() ?? Promise.resolve({ ready: false, services: [] })
  }
}

export const electronWindowBridge = new ElectronWindowBridge()
