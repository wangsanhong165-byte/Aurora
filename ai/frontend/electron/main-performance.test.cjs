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

test('main UI transition stops startup lifecycle polling', () => {
  const loadAppUrl = sourceBetween(
    'function loadAppUrl() {',
    '// ── System tray',
  )

  assert.match(loadAppUrl, /clearInterval\(statusTimer\)/)
  assert.match(loadAppUrl, /statusTimer = null/)
})

test('stable Electron runtime refreshes lifecycle only on demand', () => {
  const pollingLoop = sourceBetween(
    'statusTimer = setInterval',
    '// Now show the window',
  )
  const statusHandler = sourceBetween(
    "ipcMain.handle('get-status'",
    "ipcMain.handle('lifecycle:getSnapshot'",
  )

  assert.doesNotMatch(pollingLoop, /pm\.refresh/)
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
