#!/usr/bin/env node
'use strict'

const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const { spawn, spawnSync } = require('node:child_process')

const ROOT = path.resolve(__dirname, '..')
const FRONTEND = path.join(ROOT, 'frontend')
const CONTROL_RECORD = path.join(ROOT, 'data', 'runtime', 'lifecycle-control.json')

function readRuntimeConfig (root = ROOT) {
  const file = path.join(root, 'config', 'runtime.local.json')
  if (!fs.existsSync(file)) return { python: { default: '', services: {} } }
  const value = JSON.parse(fs.readFileSync(file, 'utf8'))
  if (typeof value.python === 'string') {
    value.python = { default: value.python, services: {} }
  }
  value.python ||= { default: '', services: {} }
  value.python.services ||= {}
  return value
}

function commandOnPath (command) {
  const result = spawnSync(process.platform === 'win32' ? 'where.exe' : 'which', [command], {
    encoding: 'utf8',
    windowsHide: true,
  })
  return result.status === 0 ? result.stdout.trim().split(/\r?\n/)[0] : ''
}

function selectPython ({
  cliPython = '',
  config = readRuntimeConfig(),
  environment = process.env,
  exists = fs.existsSync,
  which = commandOnPath,
} = {}) {
  const candidates = [
    cliPython,
    environment.MAIN_PYTHON,
    config.python?.default,
    'D:\\conda\\envs\\qwen3-asr\\python.exe',
    which('python.exe') || which('python'),
    which('py.exe'),
  ].filter(Boolean)
  return candidates.find(candidate => exists(candidate) || candidate === 'py.exe') || ''
}

function walkInputs (directory) {
  if (!fs.existsSync(directory)) return []
  return fs.readdirSync(directory, { withFileTypes: true })
    .flatMap(entry => {
      const target = path.join(directory, entry.name)
      return entry.isDirectory() ? walkInputs(target) : [target]
    })
}

function digestFiles (files, base) {
  const hash = crypto.createHash('sha256')
  for (const file of files.sort()) {
    hash.update(path.relative(base, file).replaceAll('\\', '/'))
    hash.update(fs.readFileSync(file))
  }
  return hash.digest('hex')
}

function computeBuildFingerprint (frontend = FRONTEND, nodeVersion = process.version) {
  const fixed = [
    'package.json', 'package-lock.json', 'vite.config.ts', 'vite.config.js',
    'tsconfig.json', 'tsconfig.app.json', 'index.html',
  ].map(name => path.join(frontend, name)).filter(fs.existsSync)
  const sourceFiles = [...walkInputs(path.join(frontend, 'src')), ...fixed]
  return {
    schema_version: 1,
    sourceHash: digestFiles(sourceFiles, frontend),
    nodeVersion,
  }
}

function npmInvocation (args) {
  if (process.platform !== 'win32') return { command: 'npm', args }
  return {
    command: process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe',
    args: ['/d', '/s', '/c', ['npm.cmd', ...args].join(' ')],
  }
}

function ensureFrontendBuild ({ force = false } = {}) {
  const manifestPath = path.join(FRONTEND, 'dist', '.build-manifest.json')
  const expected = computeBuildFingerprint()
  let current = null
  try { current = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) } catch (_) {}
  const indexExists = fs.existsSync(path.join(FRONTEND, 'dist', 'index.html'))
  if (!force && indexExists && current?.sourceHash === expected.sourceHash &&
      current?.nodeVersion === expected.nodeVersion) return false
  const invocation = npmInvocation(['run', 'build'])
  const result = spawnSync(invocation.command, invocation.args, {
    cwd: FRONTEND, stdio: 'inherit', windowsHide: true,
  })
  if (result.status !== 0) throw new Error(`frontend build failed (${result.status})`)
  fs.writeFileSync(manifestPath, JSON.stringify({
    ...expected, builtAt: new Date().toISOString(),
  }, null, 2))
  return true
}

function pythonArgs (python, args) {
  return path.basename(python).toLowerCase() === 'py.exe' ? ['-3', ...args] : args
}

function controlTimeoutFor (command) {
  if (command === 'start' || command === 'restart') return 480_000
  if (command === 'stop') return 30_000
  return 5_000
}

function invokeClient (python, args, { quiet = false, timeoutMs } = {}) {
  const command = args[0] || 'status'
  const result = spawnSync(python, pythonArgs(python, ['-m', 'app.lifecycle.client', ...args]), {
    cwd: ROOT,
    encoding: 'utf8',
    windowsHide: true,
    timeout: timeoutMs ?? controlTimeoutFor(command),
  })
  if (!quiet && result.stdout) process.stdout.write(result.stdout)
  if (result.error?.code === 'ETIMEDOUT') {
    if (!quiet) {
      console.error(`[FAILED] Lifecycle '${command}' timed out after ${timeoutMs ?? controlTimeoutFor(command)} ms`)
    }
    return { ...result, status: 124 }
  }
  return result
}

function waitForControl (python, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const result = invokeClient(python, ['status'], { quiet: true, timeoutMs: 5_000 })
    if (result.status === 0) return
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100)
  }
  throw new Error('Lifecycle Supervisor did not open its control endpoint')
}

function ensureSupervisor (python) {
  if (fs.existsSync(CONTROL_RECORD)) {
    const result = invokeClient(python, ['status'], { quiet: true, timeoutMs: 10_000 })
    if (result.status === 0) return
    const record = JSON.parse(fs.readFileSync(CONTROL_RECORD, 'utf8'))
    if (Number.isInteger(record.pid)) {
      let alive = false
      try {
        process.kill(record.pid, 0)
        alive = true
      } catch (error) {
        alive = error?.code === 'EPERM'
      }
      if (alive) {
        console.log(`[RECOVERY] Supervisor PID ${record.pid} is unresponsive; verifying workspace identities...`)
        const recovery = spawnSync(
          python,
          pythonArgs(python, ['-m', 'app.lifecycle.recovery', '--root', ROOT]),
          { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 30_000 },
        )
        if (recovery.stdout) process.stdout.write(recovery.stdout)
        if (recovery.status !== 0) {
          throw new Error(
            recovery.stderr?.trim() ||
            `Lifecycle Supervisor (PID ${record.pid}) could not be recovered safely.`,
          )
        }
      }
    }
  }
  const logDir = path.join(ROOT, 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  const output = fs.openSync(path.join(logDir, 'supervisor-bootstrap.log'), 'a')
  const child = spawn(python, pythonArgs(python, ['-m', 'app.lifecycle.supervisor', '--serve']), {
    cwd: ROOT,
    detached: true,
    windowsHide: true,
    stdio: ['ignore', output, output],
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
  })
  child.unref()
  waitForControl(python)
}

function doctor (python) {
  const checks = [
    ['Node.js', process.execPath, fs.existsSync(process.execPath)],
    ['Python', python, Boolean(python)],
    ['Service manifest', path.join(ROOT, 'config', 'services.json'), fs.existsSync(path.join(ROOT, 'config', 'services.json'))],
    ['Frontend package', path.join(FRONTEND, 'package.json'), fs.existsSync(path.join(FRONTEND, 'package.json'))],
  ]
  for (const [name, detail, ok] of checks) {
    console.log(`${ok ? '[OK]' : '[FAIL]'} ${name}: ${detail}`)
  }
  return checks.every(item => item[2]) ? 0 : 1
}

function holdForeground (python) {
  const keepAlive = setInterval(() => {}, 60_000)
  const stop = () => {
    clearInterval(keepAlive)
    invokeClient(python, ['stop'], { quiet: true })
    invokeClient(python, ['shutdown'], { quiet: true })
  }
  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
}

async function main (argv = process.argv.slice(2)) {
  const command = argv[0] || 'electron'
  const hot = argv.includes('--hot') || command === 'dev'
  const pythonIndex = argv.indexOf('--python')
  const python = selectPython({ cliPython: pythonIndex >= 0 ? argv[pythonIndex + 1] : '' })
  if (command === 'doctor') return doctor(python)
  if (!python) throw new Error('Python was not found. Run soulctl doctor.')

  if (['electron', 'web', 'dev'].includes(command) && !hot) ensureFrontendBuild()
  await ensureSupervisor(python)

  if (command === 'logs') {
    console.log(path.join(ROOT, 'logs', 'launches'))
    return 0
  }
  if (command === 'diagnostics') {
    const result = invokeClient(python, ['diagnostics'])
    return result.status || 0
  }

  if (command === 'electron' || command === 'dev') {
    const invocation = npmInvocation(['run', 'electron:start'])
    const child = spawn(invocation.command, invocation.args, {
      cwd: FRONTEND,
      stdio: 'inherit',
      env: {
        ...process.env,
        MAIN_PYTHON: python,
        SOULLINK_HOT: hot ? '1' : '0',
        SOULLINK_PROFILE: hot ? 'full' : 'electron',
      },
      windowsHide: false,
    })
    child.on('exit', code => {
      process.exitCode = code || 0
    })
    return 0
  }

  const mapped = ['start', 'stop', 'restart', 'status'].includes(command) ? command : 'start'
  const profile = command === 'web' ? 'backend' : 'backend'
  const ownerId = `${command}-${process.pid}`
  const launchId = crypto.randomUUID()
  const args = [mapped, '--profile', profile]
  if (['start', 'restart'].includes(mapped)) args.push('--launch-id', launchId, '--owner-id', ownerId)
  if (mapped === 'stop' && argv.includes('--all')) args.push('--all')
  const result = invokeClient(python, args)
  if (result.status !== 0) return result.status || 1
  if (mapped === 'stop') invokeClient(python, ['shutdown'], { quiet: true })
  if (command === 'web') {
    console.log('Open http://127.0.0.1:9528 (Ctrl+C stops this launch)')
    holdForeground(python)
  } else if (command === 'start' && argv.includes('--foreground')) {
    holdForeground(python)
  }
  return 0
}

if (require.main === module) {
  main().then(code => {
    process.exitCode = code || 0
  }).catch(error => {
    console.error(`[FAILED] ${error.message}`)
    console.error('Run: soulctl.cmd doctor')
    process.exitCode = 1
  })
}

module.exports = {
  controlTimeoutFor,
  computeBuildFingerprint,
  ensureFrontendBuild,
  main,
  readRuntimeConfig,
  selectPython,
  npmInvocation,
}
