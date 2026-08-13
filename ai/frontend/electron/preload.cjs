// Electron preload — exposed APIs for the renderer process
// Combines window controls + ProcessManager lifecycle APIs.

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,

  // ── Window controls ──
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  close: () => ipcRenderer.invoke('window:close'),
  setAlwaysOnTop: (value) => ipcRenderer.invoke('window:setAlwaysOnTop', value),
  setPetMode: (enabled) => ipcRenderer.invoke('window:setPetMode', enabled),
  setPetMousePassthrough: (passthrough) => ipcRenderer.send('pet:setMousePassthrough', passthrough),
  startWindowDrag: () => ipcRenderer.send('window:dragStart'),
  endWindowDrag: () => ipcRenderer.send('window:dragEnd'),
  getSettings: () => ipcRenderer.invoke('app:getSettings'),
  selectCharacterAsset: (kind) => ipcRenderer.invoke('character:selectAsset', kind),
  selectWallpaper: (mode) => ipcRenderer.invoke('wallpaper:select', mode),
  openWallpaperWorkshop: () => ipcRenderer.invoke('wallpaper:openWorkshop'),

  // ── ProcessManager / backend lifecycle ──
  getStatus: () => ipcRenderer.invoke('get-status'),
  isReady: () => ipcRenderer.invoke('is-ready'),
  restartServices: () => ipcRenderer.invoke('restart-services'),
  getLogsDir: () => ipcRenderer.invoke('get-logs-dir'),
  getServiceLog: (serviceName) => ipcRenderer.invoke('get-service-log', serviceName),
  getLifecycleSnapshot: () => ipcRenderer.invoke('lifecycle:getSnapshot'),
  lifecycleCommand: (command) => ipcRenderer.invoke('lifecycle:command', command),
  openLogs: () => ipcRenderer.invoke('lifecycle:openLogs'),
  onLifecycleSnapshot: (callback) => {
    const listener = (_event, snapshot) => callback(snapshot)
    ipcRenderer.on('lifecycle:snapshot', listener)
    return () => ipcRenderer.removeListener('lifecycle:snapshot', listener)
  },
  onPetExitRequest: (callback) => {
    const listener = () => callback()
    ipcRenderer.on('pet:exit-request', listener)
    return () => ipcRenderer.removeListener('pet:exit-request', listener)
  },
  onLifecycleError: (callback) => {
    const listener = (_event, message) => callback(message)
    ipcRenderer.on('lifecycle:error', listener)
    return () => ipcRenderer.removeListener('lifecycle:error', listener)
  },
})
