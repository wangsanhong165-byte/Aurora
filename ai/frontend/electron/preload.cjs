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
  getSettings: () => ipcRenderer.invoke('app:getSettings'),

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
  onLifecycleError: (callback) => {
    const listener = (_event, message) => callback(message)
    ipcRenderer.on('lifecycle:error', listener)
    return () => ipcRenderer.removeListener('lifecycle:error', listener)
  },
})
