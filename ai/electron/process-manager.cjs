// Thin Electron adapter. Service facts and lifecycle rules live in app/lifecycle.
const { spawn } = require('child_process')
const path = require('path')
const readline = require('readline')

const ROOT_DIR = path.resolve(__dirname, '..')
const LOG_DIR = path.join(ROOT_DIR, 'logs')

class ProcessManager {
  constructor () {
    this._supervisor = null
    this._sequence = 0
    this._pending = new Map()
    this._status = { ready: false, services: [] }
  }

  _ensureSupervisor () {
    if (this._supervisor && !this._supervisor.killed) return
    const python = process.env.MAIN_PYTHON || process.env.PYTHON || 'python'
    this._supervisor = spawn(python, ['-m', 'app.lifecycle.supervisor'], {
      cwd: ROOT_DIR,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    readline.createInterface({ input: this._supervisor.stdout }).on('line', line => {
      try {
        const message = JSON.parse(line)
        const pending = this._pending.get(message.id)
        if (!pending) return
        this._pending.delete(message.id)
        if (message.ok) {
          this._status = message.result
          pending.resolve(message.result)
        } else {
          pending.reject(new Error(message.error))
        }
      } catch (error) {
        console.error('[Lifecycle] invalid supervisor response', error)
      }
    })
    this._supervisor.on('exit', code => {
      const error = new Error(`lifecycle supervisor exited (${code})`)
      for (const pending of this._pending.values()) pending.reject(error)
      this._pending.clear()
      this._supervisor = null
      this._status = { ready: false, services: [] }
    })
    this._supervisor.on('error', error => {
      for (const pending of this._pending.values()) pending.reject(error)
      this._pending.clear()
      this._supervisor = null
    })
    this._supervisor.stderr.on('data', data => console.error(`[Lifecycle] ${data}`))
  }

  _request (command, profile) {
    this._ensureSupervisor()
    const id = `electron-${++this._sequence}`
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this._pending.delete(id)
        reject(new Error(`lifecycle ${command} timed out`))
      }, command === 'stop' ? 30000 : 300000)
      this._pending.set(id, {
        resolve: value => { clearTimeout(timer); resolve(value) },
        reject: error => { clearTimeout(timer); reject(error) },
      })
      this._supervisor.stdin.write(
        `${JSON.stringify({ id, command, profile })}\n`,
        error => {
          if (!error) return
          const pending = this._pending.get(id)
          this._pending.delete(id)
          pending?.reject(error)
        },
      )
    })
  }

  startAll () { return this._request('start', 'electron') }
  restartAll () { return this._request('restart', 'electron') }
  async stopAll () {
    if (!this._supervisor) return this._status
    try {
      return await this._request('stop', 'electron')
    } finally {
      this._supervisor.stdin.end()
    }
  }
  getStatus () { return this._status }
  isReady () { return Boolean(this._status.ready) }
  getLogsDir () { return LOG_DIR }
}

module.exports = { ProcessManager }
