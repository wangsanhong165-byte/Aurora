const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const MAIN_SOURCE = fs.readFileSync(
  path.join(__dirname, 'main.cjs'),
  'utf8',
)
const DEVELOPER_WORKSPACE_SOURCE = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'ui', 'DeveloperWorkspace.tsx'),
  'utf8',
)

function sourceBetween (start, end) {
  const afterStart = MAIN_SOURCE.split(start, 2)[1]
  assert.ok(afterStart, `missing source marker: ${start}`)
  return afterStart.split(end, 1)[0]
}

test('main UI transition stops startup lifecycle polling only after a successful load', () => {
  const loadAppUrl = sourceBetween(
    'async function loadAppUrl() {',
    '// ── System tray',
  )

  assert.match(loadAppUrl, /if \(mainUiLoaded \|\| mainUiLoading/)
  assert.match(loadAppUrl, /return mainWindow\.loadURL\(targetUrl\)\.then/)
  assert.match(loadAppUrl, /clearInterval\(statusTimer\)/)
  assert.match(loadAppUrl, /statusTimer = null/)
  assert.ok(
    loadAppUrl.indexOf('return mainWindow.loadURL(targetUrl)')
      < loadAppUrl.indexOf('clearInterval(statusTimer)'),
    'startup polling must remain active until the main UI actually loads',
  )
  assert.match(loadAppUrl, /setTimeout\(\(\) =>/)
  assert.match(loadAppUrl, /loadAppUrl\(\)/)
})

test('startup refresh is bounded and stable runtime refresh remains on demand', () => {
  const pollingLoop = sourceBetween(
    'statusTimer = setInterval',
    '// Now show the window',
  )
  const statusHandler = sourceBetween(
    "ipcMain.handle('get-status'",
    "ipcMain.handle('lifecycle:getSnapshot'",
  )

  // This timer exists only while the bootstrap page is visible; loadAppUrl()
  // clears it in the preceding regression test.  Startup may refresh the
  // cached snapshot, but must not bypass ProcessManager rate limiting.
  assert.match(pollingLoop, /pm\.refresh\(\)/)
  assert.doesNotMatch(pollingLoop, /pm\.refresh\(true\)/)
  assert.match(statusHandler, /pm\.refresh\(\)/)
})

test('renderer console capture never blocks the Electron main process', () => {
  const consoleHandler = sourceBetween(
    "mainWindow.webContents.on('console-message'",
    '// Close',
  )

  assert.doesNotMatch(consoleHandler, /appendFileSync/)
  assert.match(consoleHandler, /fs\.appendFile\(/)
  assert.match(consoleHandler, /!isDev && level < 2/)
})

test('developer diagnostics refresh only on demand and handle failures', () => {
  const handledRequests = (
    DEVELOPER_WORKSPACE_SOURCE.match(/\.catch\(recordRequestError\)/g) ?? []
  ).length

  assert.doesNotMatch(DEVELOPER_WORKSPACE_SOURCE, /window\.setInterval/)
  assert.match(DEVELOPER_WORKSPACE_SOURCE, /if \(!connected\) return/)
  assert.ok(handledRequests >= 3)
})

test('explicit application quit shuts down every registered workspace service', () => {
  const beforeQuit = sourceBetween(
    "app.on('before-quit'",
    '\n})',
  )

  assert.match(beforeQuit, /await pm\.shutdownAll\(\)/)
})
