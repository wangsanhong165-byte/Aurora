// Electron main process — window, tray, lifecycle, ProcessManager
// Manages backend services and provides frameless window + tray UX.

// Guard: ELECTRON_RUN_AS_NODE causes Electron to skip registering the
// built-in 'electron' module. require('electron') then resolves to
// node_modules/electron/index.js (a path string) instead of the API,
// and destructuring crashes with TypeError.
if (process.env.ELECTRON_RUN_AS_NODE) {
  console.error('[FATAL] ELECTRON_RUN_AS_NODE must not be set.');
  console.error('       Unset it before launching: set ELECTRON_RUN_AS_NODE=');
  process.exit(1);
}

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, screen } = require('electron')
const path = require('path')
const fs = require('fs')
const {
  fitBoundsToWorkArea,
  getPetBounds,
  selectRestorableBounds,
} = require('./pet-window.cjs')

// ProcessManager — backend service lifecycle management
const { ProcessManager } = require('../../electron/process-manager.cjs')

// ── Constants ────────────────────────────────────────────────────────

const isDev = process.env.NODE_ENV !== 'production' && (process.env.NODE_ENV === 'development' || !app.isPackaged)
const CONSOLE_LOG = path.join(__dirname, '..', 'console.log')
const ELECTRON_PID_FILE = path.join(__dirname, '..', '..', 'data', 'pids', 'electron.pid')
// Both dev and prod load from Bridge (9528) — it serves frontend dist/ AND
// Live2D model files. Vite (5173) doesn't have the /live2d-models/ mount.
const DEV_URL = process.env.BRIDGE_URL || 'http://127.0.0.1:9528'
const PROD_URL = process.env.BRIDGE_URL || 'http://127.0.0.1:9528'

// ── State ────────────────────────────────────────────────────────────

const pm = new ProcessManager()
let mainWindow = null
let tray = null
let alwaysOnTop = false
let petMode = false
let normalWindowState = null
let forceQuit = false
let ready = false
let shutdownStarted = false

// ── Window creation ──

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false,                      // Frameless for custom title bar
    transparent: true,                 // Transparent background support
    backgroundColor: '#00000000',       // Fully transparent
    title: 'Monika Companion',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  })

  // Capture console output from the renderer process
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    const prefix = ['', 'LOG', 'WARN', 'ERR'][level] || 'LOG'
    try {
      fs.appendFileSync(CONSOLE_LOG, `[${prefix}] ${message}\n`)
    } catch (_) {}
  })

  // Close → hide to tray (not quit), unless forceQuit is set
  mainWindow.on('close', (event) => {
    if (!forceQuit) {
      event.preventDefault()
      mainWindow.hide()
      return false
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function loadAppUrl() {
  // Load the app URL (only call AFTER services are ready)
  const targetUrl = isDev ? DEV_URL : PROD_URL
  mainWindow.loadURL(targetUrl)
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })
}

// ── System tray ──

function createTray() {
  // Try to find an icon, fall back to empty
  let icon
  const iconPath = path.join(__dirname, '..', '..', 'electron', 'tray-icon.png')
  if (fs.existsSync(iconPath)) {
    icon = nativeImage.createFromPath(iconPath)
  } else {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('Monika Companion')

  const contextMenu = Menu.buildFromTemplate([
    { label: '显示窗口', click: () => mainWindow?.show() },
    { label: '隐藏窗口', click: () => mainWindow?.hide() },
    { type: 'separator' },
    {
      label: '置顶显示',
      type: 'checkbox',
      checked: alwaysOnTop,
      click: (menuItem) => {
        alwaysOnTop = menuItem.checked
        if (mainWindow) {
          mainWindow.setAlwaysOnTop(petMode || alwaysOnTop)
        }
      },
    },
    { type: 'separator' },
    { label: '退出', click: () => {
      forceQuit = true
      app.quit()
    }},
  ])

  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => mainWindow?.show())
}

// ── IPC handlers (window controls) ──

function setupIPC() {
  // Window controls (from existing UI)
  ipcMain.handle('window:minimize', () => {
    mainWindow?.minimize()
  })

  ipcMain.handle('window:close', () => {
    mainWindow?.close()
  })

  ipcMain.handle('window:setAlwaysOnTop', (_event, value) => {
    alwaysOnTop = value
    if (mainWindow) {
      mainWindow.setAlwaysOnTop(petMode || value)
    }
    return alwaysOnTop
  })

  ipcMain.handle('window:setPetMode', (_event, enabled) => {
    if (!mainWindow) return { enabled: false }
    if (enabled && !petMode) {
      const currentBounds = mainWindow.getBounds()
      const maximized = mainWindow.isMaximized()
      const fullScreen = mainWindow.isFullScreen()
      const bounds = selectRestorableBounds({
        current: currentBounds,
        normal: mainWindow.getNormalBounds(),
        maximized,
        fullScreen,
      })
      normalWindowState = {
        bounds,
        maximized,
        fullScreen,
      }
      if (normalWindowState.fullScreen) mainWindow.setFullScreen(false)
      if (normalWindowState.maximized) mainWindow.unmaximize()
      const display = screen.getDisplayMatching(bounds)
      const petBounds = getPetBounds(display.workArea)
      mainWindow.setMinimumSize(
        Math.min(320, petBounds.width),
        Math.min(480, petBounds.height),
      )
      mainWindow.setBounds(petBounds, true)
      mainWindow.setIgnoreMouseEvents(false)
      mainWindow.setAlwaysOnTop(true)
      petMode = true
    } else if (!enabled && petMode) {
      mainWindow.setIgnoreMouseEvents(false)
      mainWindow.setMinimumSize(800, 600)
      if (normalWindowState) {
        const display = screen.getDisplayMatching(normalWindowState.bounds)
        mainWindow.setBounds(
          fitBoundsToWorkArea(normalWindowState.bounds, display.workArea),
          true,
        )
        if (normalWindowState.maximized) mainWindow.maximize()
        if (normalWindowState.fullScreen) mainWindow.setFullScreen(true)
      }
      mainWindow.setAlwaysOnTop(alwaysOnTop)
      petMode = false
    }
    return { enabled: petMode, bounds: mainWindow.getBounds() }
  })

  ipcMain.handle('app:getSettings', () => {
    return {
      alwaysOnTop,
      platform: process.platform,
    }
  })

  // ProcessManager / lifecycle IPC (new)
  ipcMain.handle('get-status', () => {
    return pm.getStatus()
  })

  ipcMain.handle('get-logs-dir', () => {
    return pm.getLogsDir()
  })

  ipcMain.handle('restart-services', async () => {
    await pm.restartAll()
    return { ok: true }
  })

  ipcMain.handle('is-ready', () => {
    return pm.isReady()
  })

  ipcMain.handle('get-service-log', async (_event, serviceName) => {
    const logPath = path.join(pm.getLogsDir(), `${serviceName}.log`)
    try {
      const content = fs.readFileSync(logPath, 'utf-8')
      const lines = content.split('\n').slice(-100)
      return { ok: true, lines }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  })
}

// ── App lifecycle ──

app.whenReady().then(async () => {
  fs.mkdirSync(path.dirname(ELECTRON_PID_FILE), { recursive: true })
  fs.writeFileSync(ELECTRON_PID_FILE, String(process.pid), 'utf8')
  // Clear previous console log
  try { fs.unlinkSync(CONSOLE_LOG) } catch (_) {}

  setupIPC()
  createWindow()       // Create frameless window (hidden, no URL loaded)
  createTray()

  if (isDev) {
    console.log('[Electron] Dev mode — starting backend services...')
  }

  // Start all backend services before loading the frontend,
  // so the page never sees ERR_CONNECTION_REFUSED
  try {
    await pm.startAll()
    ready = true

    if (isDev) {
      const status = pm.getStatus()
      console.log('[Electron] Service status:', JSON.stringify(status, null, 2))
    }

    // Now that services are ready, load the app
    loadAppUrl()
  } catch (err) {
    console.error('[Electron] Failed to start services:', err)
    // Still try to load the page (bridge might be running despite error)
    loadAppUrl()
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    } else {
      mainWindow?.show()
    }
  })
})

app.on('window-all-closed', () => {
  // On Windows: tray keeps running — only forceQuit exits completely
})

app.on('before-quit', async (event) => {
  if (shutdownStarted) return
  event.preventDefault()
  shutdownStarted = true
  if (isDev) {
    console.log('[Electron] Shutting down all services...')
  }

  try {
    await pm.stopAll()
  } catch (err) {
    console.error('[Electron] Lifecycle shutdown failed:', err)
  } finally {
    try { fs.unlinkSync(ELECTRON_PID_FILE) } catch (_) {}
    app.exit(0)
  }
})
