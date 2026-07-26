// ProcessManager — unified backend service lifecycle for Companion.
// Spawns all subprocesses with windowsHide:true, tracks PIDs,
// manages log output, provides clean shutdown.
// v2 — fixes: per-service cwd, port cleanup, graceful failure.

const { spawn, execSync } = require('child_process')
const path = require('path')
const fs = require('fs')

// ── Paths ────────────────────────────────────────────────────────────

const ROOT_DIR = path.resolve(__dirname, '..')
const LOG_DIR = path.join(ROOT_DIR, 'logs')
const CONFIG_DIR = path.join(ROOT_DIR, 'config')
const GSVI_DIR = path.join(ROOT_DIR, 'models', 'tts', 'GPT-SoVITS-v2pro-20250604-nvidia50')
const GSVI_PYTHON = path.join(GSVI_DIR, 'runtime', 'python.exe')
const MAIN_PYTHON = 'C:\\ProgramData\\miniconda3\\envs\\qwen3-asr\\python.exe'
const GSVI_CONFIG = path.join(GSVI_DIR, 'GPT_SoVITS', 'configs', 'tts_infer.yaml')
const ENV_FILE = path.join(CONFIG_DIR, '.env')

function _isDev () {
  return process.env.NODE_ENV === 'development' || !process.env.NODE_ENV
}

// ── Service config loader (reads config/services.json) ──

const SERVICES_JSON = path.join(CONFIG_DIR, 'services.json')

let _svcConfig = null

function _loadSvcConfig () {
  if (_svcConfig) return _svcConfig
  try {
    const raw = fs.readFileSync(SERVICES_JSON, 'utf-8')
    _svcConfig = JSON.parse(raw)
    // Strip _meta
    for (const k of Object.keys(_svcConfig)) {
      if (k.startsWith('_')) delete _svcConfig[k]
    }
  } catch (err) {
    console.warn('[ProcessManager] Failed to read services.json, fallback:', err.message)
    // Hard-coded fallback (same as DEFAULT_FALLBACKS in Python service_config)
    _svcConfig = {
      asr: { host: '127.0.0.1', port: 9101, health: '/health' },
      llm: { host: '127.0.0.1', port: 9102, health: '/health' },
      tts: { host: '127.0.0.1', port: 9103, health: '/health' },
      memory: { host: '127.0.0.1', port: 9104, health: '/health' },
      gsvi: { host: '127.0.0.1', port: 9105, health: '/health' },
      bridge: { host: '127.0.0.1', port: 9528, health: '/health' },
      frontend: { host: 'localhost', port: 5173, health: '/' },
    }
  }
  return _svcConfig
}

function _svcPort (name) {
  const env = process.env[`${name.toUpperCase()}_PORT`]
  if (env) return parseInt(env, 10)
  const cfg = _loadSvcConfig()
  return (cfg[name] && cfg[name].port) || 0
}

function _svcHost (name) {
  const envUrl = process.env[`${name.toUpperCase()}_URL`]
  if (envUrl) {
    try { return new URL(envUrl).hostname } catch (_) {}
  }
  const cfg = _loadSvcConfig()
  return (cfg[name] && cfg[name].host) || '127.0.0.1'
}

function _svcHealth (name) {
  const cfg = _loadSvcConfig()
  return (cfg[name] && cfg[name].health) || '/health'
}

// ── Build SERVICE_DEFINITIONS from config ──

const SERVICE_DEFINITIONS = [
  {
    name: 'asr',
    module: 'app.modules.asr.api',
    port: _svcPort('asr'),
    envVar: 'ASR_PORT',
    python: MAIN_PYTHON,
    args: ['--host', _svcHost('asr')],
    cwd: ROOT_DIR,
    startupProbe: _svcHealth('asr'),
  },
  {
    name: 'llm',
    module: 'app.modules.llm.api',
    port: _svcPort('llm'),
    envVar: 'LLM_PORT',
    python: MAIN_PYTHON,
    args: ['--host', _svcHost('llm'), '--env-file', ENV_FILE],
    cwd: ROOT_DIR,
    startupProbe: _svcHealth('llm'),
  },
  {
    name: 'tts',
    module: 'app.modules.tts.api',
    port: _svcPort('tts'),
    envVar: 'TTS_PORT',
    python: MAIN_PYTHON,
    args: ['--host', _svcHost('tts'), '--env-file', ENV_FILE],
    cwd: ROOT_DIR,
    startupProbe: _svcHealth('tts'),
  },
  {
    name: 'memory',
    module: 'app.modules.memory.api',
    port: _svcPort('memory'),
    envVar: 'MEMORY_PORT',
    python: MAIN_PYTHON,
    args: ['--host', _svcHost('memory')],
    cwd: ROOT_DIR,
    startupProbe: _svcHealth('memory'),
  },
  {
    name: 'gsvi',
    type: 'script',
    script: 'api_v2.py',
    port: _svcPort('gsvi'),
    envVar: 'GSVI_PORT',
    python: GSVI_PYTHON,
    args: ['-a', _svcHost('gsvi'), '-p', String(_svcPort('gsvi')), '-c', GSVI_CONFIG],
    cwd: GSVI_DIR,
    startupProbe: _svcHealth('gsvi'),
  },
  {
    name: 'bridge',
    module: 'app.bridge.server',
    port: _svcPort('bridge'),
    envVar: 'BRIDGE_PORT',
    python: MAIN_PYTHON,
    args: [],
    cwd: ROOT_DIR,
    startupProbe: _svcHealth('bridge'),
  },
]

// Vite dev server — only in development mode
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend')
const VITE_BIN = path.join(FRONTEND_DIR, 'node_modules', 'vite', 'bin', 'vite.js')
if (_isDev() && fs.existsSync(VITE_BIN)) {
  SERVICE_DEFINITIONS.push({
    name: 'vite',
    type: 'script',
    script: VITE_BIN,
    port: _svcPort('frontend'),
    envVar: 'VITE_PORT',
    python: 'node',
    args: [],
    cwd: FRONTEND_DIR,
    startupProbe: _svcHealth('frontend'),
  })
}

const SERVICE_TIMEOUTS = { asr: 60, gsvi: 180, tts: 120, default: 30 }
const HEALTH_INTERVAL_MS = 10000
const HEALTH_FAILURE_THRESHOLD = 3
const RESTART_WINDOW_MS = 5 * 60 * 1000
const MAX_RESTARTS_PER_WINDOW = 3
const MAX_LOG_BYTES = 5 * 1024 * 1024
const LOG_BACKUPS = 3

// ── ProcessManager class ─────────────────────────────────────────────

class ProcessManager {
  constructor () {
    this._processes = new Map() // name → { proc, pid, status, startTime }
    this._ready = false
    this._stopping = false
    this._healthTimer = null
    this._healthCheckRunning = false
    this._ensureLogDir()
  }

  // ── Internal helpers ──

  _ensureLogDir () {
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true })
    }
  }

  _logPath (name) {
    return path.join(LOG_DIR, `${name}.log`)
  }

  _getEnv (svc) {
    const env = { ...process.env }
    env.PYTHONIOENCODING = 'utf-8'
    env.PYTHONUTF8 = '1'
    env.BROWSER = 'none'

    // GSVI runtime needs its own runtime/ dir in PATH for CUDA DLLs
    if (svc.name === 'gsvi' && svc.cwd) {
      const runtimeDir = path.join(svc.cwd, 'runtime')
      env.PATH = `${runtimeDir};${env.PATH || ''}`
    }

    // Apply port overrides from current env
    if (process.env[svc.envVar]) {
      const overridePort = process.env[svc.envVar]
      const pIdx = svc.args.indexOf('-p')
      if (pIdx !== -1 && pIdx + 1 < svc.args.length) {
        svc.args[pIdx + 1] = overridePort
      } else if (svc.port) {
        svc.port = parseInt(overridePort, 10)
      }
    }

    return env
  }

  _buildCommand (svc) {
    if (svc.type === 'script') {
      return [svc.python, svc.script, ...svc.args]
    }
    return [svc.python, '-m', svc.module, '--port', String(svc.port), ...svc.args]
  }

  _logFileStream (name) {
    const logPath = this._logPath(name)
    this._rotateLog(logPath)
    return fs.createWriteStream(logPath, { flags: 'a', encoding: 'utf-8' })
  }

  _rotateLog (logPath) {
    try {
      if (!fs.existsSync(logPath) || fs.statSync(logPath).size < MAX_LOG_BYTES) return
      for (let index = LOG_BACKUPS; index >= 1; index--) {
        const source = index === 1 ? logPath : `${logPath}.${index - 1}`
        const target = `${logPath}.${index}`
        if (!fs.existsSync(source)) continue
        if (fs.existsSync(target)) fs.unlinkSync(target)
        fs.renameSync(source, target)
      }
    } catch (err) {
      console.warn(`[ProcessManager] Log rotation failed: ${err.message}`)
    }
  }

  _timestamp () {
    return new Date().toISOString()
  }

  _setStatus (name, status, data) {
    const entry = this._processes.get(name)
    if (entry) {
      entry.status = status
      if (data) Object.assign(entry, data)
    }
  }

  // ── Port cleanup ──

  _killProcessOnPort (port) {
    // Windows: find PID using the port, then kill it
    try {
      const result = execSync(
        `netstat -ano | find ":${port}" | find "LISTENING"`,
        { encoding: 'utf-8', timeout: 3000 }
      )
      const lines = result.trim().split('\n')
      for (const line of lines) {
        const parts = line.trim().split(/\s+/)
        const pid = parts[parts.length - 1]
        if (pid && pid !== '0') {
          try {
            execSync(`taskkill /PID ${pid} /T /F 2>nul`, { stdio: 'ignore', timeout: 3000 })
            console.log(`[ProcessManager] Killed existing process ${pid} on port ${port}`)
          } catch {
            // Process may already be dead
          }
        }
      }
    } catch {
      // No process on this port — good
    }
  }

  // ── Service start (single) ──

  async _startService (svc) {
    const { name } = svc

    if (this._processes.has(name) && this._processes.get(name).status === 'running') {
      return
    }

    // Kill existing process on this port before spawning
    this._killProcessOnPort(svc.port)

    const cmd = this._buildCommand(svc)
    const env = this._getEnv(svc)
    const logStream = this._logFileStream(name)
    const spawnOpts = {
      cwd: svc.cwd || ROOT_DIR,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    }

    const previous = this._processes.get(name)
    const entry = {
      proc: null,
      pid: null,
      status: 'starting',
      startTime: Date.now(),
      logStream,
      consecutiveHealthFailures: 0,
      lastHealthAt: 0,
      lastHealthError: '',
      restartHistory: previous?.restartHistory || [],
    }
    this._processes.set(name, entry)

    logStream.write(`[${this._timestamp()}] Starting: ${cmd.join(' ')}\n`)
    logStream.write(`[${this._timestamp()}] cwd: ${spawnOpts.cwd}\n`)

    try {
      const proc = spawn(cmd[0], cmd.slice(1), spawnOpts)
      entry.proc = proc
      entry.pid = proc.pid

      proc.stdout.on('data', (data) => {
        logStream.write(data.toString())
      })

      proc.stderr.on('data', (data) => {
        logStream.write(data.toString())
      })

      proc.on('error', (err) => {
        logStream.write(`[${this._timestamp()}] Spawn error: ${err.message}\n`)
        entry.status = 'error'
      })

      proc.on('exit', (code, signal) => {
        const msg = `[${this._timestamp()}] Exited code=${code} signal=${signal}\n`
        logStream.write(msg)
        entry.status = code === 0 ? 'stopped' : 'error'
        entry.exitCode = code
        logStream.end()
      })

      this._setStatus(name, 'running', { pid: proc.pid })
    } catch (err) {
      logStream.write(`[${this._timestamp()}] Failed to spawn: ${err.message}\n`)
      entry.status = 'error'
      logStream.end()
    }
  }

  // ── Wait for service readiness ──

  async _waitForService (svc) {
    const { name, port, startupProbe } = svc
    const timeout = SERVICE_TIMEOUTS[name] || SERVICE_TIMEOUTS.default
    const probePath = startupProbe || ''
    const url = `http://127.0.0.1:${port}${probePath}`
    const http = require('http')
    const start = Date.now()

    const entry = this._processes.get(name)
    const logStream = entry?.logStream

    while (Date.now() - start < timeout * 1000) {
      // If process crashed, don't keep waiting
      if (entry && entry.status === 'error') {
        const msg = `[${this._timestamp()}] ${name} process exited before ready\n`
        if (logStream) logStream.write(msg)
        return false
      }

      try {
        await new Promise((resolve, reject) => {
          const req = http.get(url, (res) => {
            let body = ''
            res.setEncoding('utf8')
            res.on('data', chunk => { body += chunk })
            res.on('end', () => {
              if (res.statusCode !== 200 && res.statusCode !== 404) {
                reject(new Error(`status ${res.statusCode}`))
                return
              }
              if (res.statusCode === 200 && body) {
                try {
                  const payload = JSON.parse(body)
                  if (payload.ready === false) {
                    reject(new Error('model not ready'))
                    return
                  }
                } catch (err) {
                  if (err.message === 'model not ready') {
                    reject(err)
                    return
                  }
                }
              }
              resolve()
            })
          })
          req.on('error', reject)
          req.setTimeout(2000, () => { req.destroy(); reject(new Error('timeout')) })
        })

        const elapsed = ((Date.now() - start) / 1000).toFixed(1)
        const msg = `[${this._timestamp()}] ${name} ready (${elapsed}s)\n`
        if (logStream) logStream.write(msg)
        return true
      } catch {
        await new Promise(r => setTimeout(r, 500))
      }
    }

    const msg = `[${this._timestamp()}] ${name} NOT ready after ${timeout}s timeout\n`
    if (logStream) logStream.write(msg)
    return false
  }

  // ── Public API ──

  _probeService (svc, timeoutMs = 2000) {
    const http = require('http')
    const probePath = svc.startupProbe || ''
    const url = `http://127.0.0.1:${svc.port}${probePath}`
    return new Promise((resolve, reject) => {
      const req = http.get(url, (res) => {
        let body = ''
        res.setEncoding('utf8')
        res.on('data', chunk => { body += chunk })
        res.on('end', () => {
          if (res.statusCode !== 200 && res.statusCode !== 404) {
            reject(new Error(`status ${res.statusCode}`))
            return
          }
          if (res.statusCode === 200 && body) {
            try {
              const payload = JSON.parse(body)
              if (payload.ready === false) {
                reject(new Error('service not ready'))
                return
              }
            } catch (err) {
              if (err.message === 'service not ready') {
                reject(err)
                return
              }
            }
          }
          resolve()
        })
      })
      req.on('error', reject)
      req.setTimeout(timeoutMs, () => req.destroy(new Error('health timeout')))
    })
  }

  _startHealthMonitor () {
    if (this._healthTimer) return
    this._healthTimer = setInterval(() => {
      void this._runHealthChecks()
    }, HEALTH_INTERVAL_MS)
    this._healthTimer.unref?.()
  }

  _stopHealthMonitor () {
    if (this._healthTimer) clearInterval(this._healthTimer)
    this._healthTimer = null
  }

  async _runHealthChecks () {
    if (this._stopping || this._healthCheckRunning) return
    this._healthCheckRunning = true
    try {
      for (const svc of SERVICE_DEFINITIONS) {
        const entry = this._processes.get(svc.name)
        if (!entry || entry.status === 'starting' || entry.status === 'restarting') continue
        if (entry.status === 'error') {
          await this._recoverService(svc, 'process exited')
          continue
        }
        if (entry.status !== 'running') continue
        try {
          await this._probeService(svc)
          entry.consecutiveHealthFailures = 0
          entry.lastHealthAt = Date.now()
          entry.lastHealthError = ''
        } catch (err) {
          entry.consecutiveHealthFailures = (entry.consecutiveHealthFailures || 0) + 1
          entry.lastHealthAt = Date.now()
          entry.lastHealthError = err.message
          if (entry.consecutiveHealthFailures >= HEALTH_FAILURE_THRESHOLD) {
            await this._recoverService(svc, err.message)
          }
        }
      }
    } finally {
      this._healthCheckRunning = false
    }
  }

  async _recoverService (svc, reason) {
    if (this._stopping) return false
    const entry = this._processes.get(svc.name)
    if (!entry || entry.status === 'restarting') return false
    const now = Date.now()
    entry.restartHistory = (entry.restartHistory || [])
      .filter(timestamp => now - timestamp < RESTART_WINDOW_MS)
    if (entry.restartHistory.length >= MAX_RESTARTS_PER_WINDOW) {
      entry.status = 'restart_suppressed'
      entry.lastHealthError = `restart limit reached: ${reason}`
      console.error(`[ProcessManager] ${svc.name}: restart suppressed (${reason})`)
      return false
    }
    entry.restartHistory.push(now)
    entry.status = 'restarting'
    const attempt = entry.restartHistory.length
    const delayMs = Math.min(15000, 1000 * (2 ** (attempt - 1)))
    console.warn(`[ProcessManager] ${svc.name}: unhealthy (${reason}), restart in ${delayMs}ms`)
    await new Promise(resolve => setTimeout(resolve, delayMs))
    if (this._stopping) return false
    await this._stopService(svc.name)
    await this._startService(svc)
    const ready = await this._waitForService(svc)
    const fresh = this._processes.get(svc.name)
    if (fresh) {
      fresh.restartHistory = entry.restartHistory
      fresh.consecutiveHealthFailures = 0
      fresh.lastHealthAt = Date.now()
      if (!ready) fresh.status = 'error'
    }
    return ready
  }

  _service (name) {
    return SERVICE_DEFINITIONS.find(svc => svc.name === name)
  }

  async _startAndWait (name) {
    const svc = this._service(name)
    if (!svc) return false
    console.log(`[ProcessManager] Starting ${name}...`)
    await this._startService(svc)
    const ready = await this._waitForService(svc)
    console.log(`[ProcessManager] ${name}: ${ready ? 'ready' : 'failed'}`)
    return ready
  }

  _postJson (url, payload, timeoutMs) {
    const http = require('http')
    const body = JSON.stringify(payload)
    return new Promise((resolve, reject) => {
      const target = new URL(url)
      const req = http.request({
        hostname: target.hostname,
        port: target.port,
        path: target.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      }, res => {
        let responseBody = ''
        res.setEncoding('utf8')
        res.on('data', chunk => { responseBody += chunk })
        res.on('end', () => {
          if (res.statusCode === 200) resolve(responseBody)
          else reject(new Error(`warmup status ${res.statusCode}: ${responseBody.slice(0, 200)}`))
        })
      })
      req.setTimeout(timeoutMs, () => req.destroy(new Error('warmup timeout')))
      req.on('error', reject)
      req.end(body)
    })
  }

  async _warmupTTS () {
    const tts = this._service('tts')
    const timeout = (SERVICE_TIMEOUTS.tts || 120) * 1000
    const url = `http://127.0.0.1:${tts.port}/warmup`
    const entry = this._processes.get('tts')
    try {
      console.log('[ProcessManager] Warming TTS GPU inference...')
      await this._postJson(url, {}, timeout)
      entry?.logStream?.write(`[${this._timestamp()}] tts GPU warmup complete\n`)
      console.log('[ProcessManager] TTS GPU inference: warm')
      return true
    } catch (err) {
      entry?.logStream?.write(`[${this._timestamp()}] tts GPU warmup failed: ${err.message}\n`)
      console.error(`[ProcessManager] TTS GPU warmup failed: ${err.message}`)
      return false
    }
  }

  async startAll () {
    console.log('[ProcessManager] Starting all services...')
    this._stopping = false
    this._ensureLogDir()

    // GPU services are sequential: avoid allocation races and only expose the
    // UI after model weights and first-inference kernels are resident.
    const results = []
    results.push(await this._startAndWait('gsvi'))
    results.push(await this._startAndWait('tts'))
    results.push(await this._warmupTTS())
    results.push(await this._startAndWait('asr'))

    const remaining = SERVICE_DEFINITIONS.filter(
      svc => !['gsvi', 'tts', 'asr'].includes(svc.name),
    )
    await Promise.all(remaining.map(svc => this._startService(svc)))
    results.push(...await Promise.all(remaining.map(svc => this._waitForService(svc))))

    const failed = results.filter(r => !r).length
    const readyCnt = results.filter(r => r).length

    if (failed > 0) {
      console.warn(`[ProcessManager] ${readyCnt} ready, ${failed} failed`)
    } else {
      this._ready = true
      console.log('[ProcessManager] All services and GPU models ready')
    }
    console.log(`[ProcessManager] Startup gates: ${readyCnt}/${results.length} ready`)
    this._startHealthMonitor()
  }

  async stopAll () {
    console.log('[ProcessManager] Stopping all services...')
    this._stopping = true
    this._stopHealthMonitor()
    const stopOrder = ['bridge', 'gsvi', 'tts', 'llm', 'asr', 'memory']

    for (const name of stopOrder) {
      await this._stopService(name)
    }

    this._ready = false
    console.log('[ProcessManager] All services stopped')
  }

  async _stopService (name) {
    const entry = this._processes.get(name)
    if (!entry || !entry.proc || entry.status === 'stopped') return

    const { proc, logStream } = entry
    const pid = proc.pid

    if (logStream) {
      logStream.write(`[${this._timestamp()}] Stopping pid=${pid}...\n`)
    }

    // Phase 1: force kill
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /PID ${pid} /T /F 2>nul`, { stdio: 'ignore' })
      } else {
        proc.kill('SIGTERM')
      }
    } catch {
      // May fail if process already dead
    }

    // Phase 2: wait up to 5s for exit
    const start = Date.now()
    const timeout = 5000
    await new Promise((resolve) => {
      const check = setInterval(() => {
        try {
          const result = execSync(`tasklist /FI "PID eq ${pid}" 2>nul`, { encoding: 'utf-8' })
          if (!result.includes(String(pid))) {
            clearInterval(check)
            resolve()
            return
          }
        } catch {
          clearInterval(check)
          resolve()
          return
        }

        if (Date.now() - start > timeout) {
          clearInterval(check)
          resolve()
        }
      }, 200)
    })

    entry.status = 'stopped'
    entry.pid = null
    entry.proc = null
    if (logStream) {
      logStream.write(`[${this._timestamp()}] pid=${pid} stopped\n`)
      logStream.end()
    }
  }

  restartAll () {
    return this.stopAll().then(() => this.startAll())
  }

  getStatus () {
    const services = []
    for (const [name, entry] of this._processes) {
      services.push({
        name,
        pid: entry.pid,
        status: entry.status,
        uptime: entry.startTime ? Date.now() - entry.startTime : 0,
        consecutiveHealthFailures: entry.consecutiveHealthFailures || 0,
        lastHealthAt: entry.lastHealthAt || 0,
        lastHealthError: entry.lastHealthError || '',
        restartCount: (entry.restartHistory || []).length,
      })
    }
    return {
      ready: this._ready,
      services,
    }
  }

  isReady () {
    return this._ready
  }

  getLogsDir () {
    return LOG_DIR
  }
}

module.exports = { ProcessManager }
