declare global {
  interface Window {
    electronAPI?: {
      platform: string
      minimize: () => void
      maximize: () => Promise<boolean> | boolean
      isMaximized: () => Promise<boolean> | boolean
      close: () => void
      setAlwaysOnTop: (value: boolean) => void
      setPetMode: (enabled: boolean) => void | Promise<unknown>
      setPetMousePassthrough: (passthrough: boolean) => void
      startWindowDrag: () => void
      endWindowDrag: () => void
      getSettings: () => Record<string, unknown>
      onPetExitRequest?: (callback: () => void) => () => void
      selectCharacterAsset?: (kind: string) => Promise<string>
      selectWallpaper?: (mode: 'file' | 'directory') => Promise<WallpaperResourceResult>
      openWallpaperWorkshop?: () => Promise<{ ok: boolean; path?: string; message?: string }>
      getStatus?: () => Promise<{ services?: Array<Record<string, unknown>> }>
      onLifecycleSnapshot?: (callback: (snapshot: {
        availability?: string
        services?: Array<Record<string, unknown>>
      }) => void) => () => void
    }
  }
}

export interface WallpaperResourceResult {
  ok: boolean
  code?: string
  message?: string
  path?: string
  url?: string
  type?: 'image' | 'video'
  sourceType?: string
  label?: string
  previewFallback?: boolean
  warning?: string
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
  setPetMousePassthrough(value: boolean) { return window.electronAPI?.setPetMousePassthrough?.(value) }
  onPetExitRequest(callback: () => void) { return window.electronAPI?.onPetExitRequest?.(callback) ?? (() => {}) }
  startWindowDrag() { return window.electronAPI?.startWindowDrag?.() }
  endWindowDrag() { return window.electronAPI?.endWindowDrag?.() }
  selectWallpaper(mode: 'file' | 'directory') {
    return window.electronAPI?.selectWallpaper?.(mode) ?? Promise.resolve({ ok: false, code: 'unavailable' })
  }
  openWallpaperWorkshop() {
    return window.electronAPI?.openWallpaperWorkshop?.() ?? Promise.resolve({ ok: false, message: '仅桌面版支持此功能。' })
  }
  getStatus() {
    return window.electronAPI?.getStatus?.() ?? Promise.resolve({ ready: false, services: [] })
  }
}

export const electronWindowBridge = new ElectronWindowBridge()
