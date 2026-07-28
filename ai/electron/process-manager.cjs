'use strict'

const crypto = require('node:crypto')
const path = require('node:path')
const { spawn } = require('node:child_process')

const ROOT_DIR = path.resolve(__dirname, '..')

// Minimum interval between full subprocess spawns for status (ms)
const MIN_REFRESH_INTERVAL = 15_000

class ProcessManager {
  constructor () {
    this.python = process.env.MAIN_PYTHON || process.env.PYTHON || 'python'
    this.launchId = crypto.randomUUID()
    this.ownerId = `electron-${process.pid}-${crypto.randomUUID()}`
    this.profile = process.env.SOULLINK_PROFILE || 'electron'
    this.ownsLaunch = false
    this._status = { availability: 'BLOCKED', services: [], capabilities: [] }
    this._refreshPromise = null
    this._lastRefreshTimestamp = 0
  }

  _request (command, extra = {}) {
    const args = [
      '-m', 'app.lifecycle.client', command,
      '--launch-id', this.launchId,
      '--owner-id', this.ownerId,
      ...Object.entries(extra).flatMap(([key, value]) => [`--${key}`, String(value)]),
    ]
    return new Promise((resolve, reject) => {
      const child = spawn(this.python, args, {
        cwd: ROOT_DIR,
        windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      })
      let stdout = ''
      let stderr = ''
      child.stdout.on('data', data => { stdout += data })
      child.stderr.on('data', data => { stderr += data })
      child.on('error', reject)
      child.on('exit', code => {
        try {
          const response = JSON.parse(stdout.trim())
          if (!response.ok) throw new Error(response.error || 'lifecycle request failed')
          this._status = response.result
          if (command === 'start') {
            this.ownsLaunch = response.result.launch_id === this.launchId
          }
          resolve(response.result)
        } catch (error) {
          reject(new Error(stderr.trim() || error.message || `lifecycle client exited (${code})`))
        }
      })
    })
  }

  startAll () { return this._request('start', { profile: this.profile }) }
  restartAll () { return this._request('restart', { profile: this.profile }) }
  async stopAll () {
    if (!this.ownsLaunch) return this._status
    await this._request('stop')
    return this._request('shutdown')
  }

  /** Full refresh: spawns a Python subprocess to query lifecycle status.
   *  Rate-limited to MIN_REFRESH_INTERVAL between calls; returns cached
   *  status if called too frequently.
   *  Pass forceFresh=true to bypass the rate limit. */
  refresh (forceFresh = false) {
    const now = Date.now()
    if (!forceFresh && (now - this._lastRefreshTimestamp) < MIN_REFRESH_INTERVAL) {
      return Promise.resolve(this._status)
    }

    if (!this._refreshPromise) {
      this._lastRefreshTimestamp = now
      this._refreshPromise = this._request('status')
        .catch(() => this._status)
        .finally(() => {
          this._refreshPromise = null
        })
    }
    return this._refreshPromise
  }

  /** Returns cached status without spawning any subprocess. */
  getStatus () { return this._status }

  isReady () { return this._status.availability !== 'BLOCKED' }

  getLogsDir () {
    return path.join(ROOT_DIR, 'logs', 'launches', this.launchId)
  }
}

module.exports = { ProcessManager }
