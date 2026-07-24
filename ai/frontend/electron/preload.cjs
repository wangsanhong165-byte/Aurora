// Electron preload — exposed APIs for the renderer process
// Combines window controls + ProcessManager lifecycle APIs.

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,

  // ── Window controls ──
  minimize: () => ipcRenderer.invoke('window:minimize'),
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
})
