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
  if (command === 'start' || command === 'restart') return 180_000
  if (command === 'stop') return 30_000
  return 5_000
}

function classifyControlState ({
  record,
  statusOk,
  processInfo = null,
  identityMatches = false,
}) {
  if (!record) return { state: 'missing' }
  if (statusOk) return { state: 'reusable' }
  if (!processInfo) return { state: 'stale' }
  if (!identityMatches) return { state: 'unverified' }
  return { state: 'recoverable' }
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
    const result = invokeClient(python, ['status'], { quiet: true, timeoutMs: 800 })
    if (result.status === 0) return
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100)
  }
  throw new Error('Lifecycle Supervisor did not open its control endpoint')
}

function readControlRecord (controlRecord = CONTROL_RECORD) {
  if (!fs.existsSync(controlRecord)) return null
  try {
    return JSON.parse(fs.readFileSync(controlRecord, 'utf8'))
  } catch (error) {
    throw new Error(`control_record_invalid: ${error.message}`)
  }
}

function parseJsonOutput (result) {
  const lines = String(result?.stdout || '').trim().split(/\r?\n/).filter(Boolean)
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      return JSON.parse(lines[index])
    } catch (_) {}
  }
  return null
}

function inspectSupervisor (python, pid, invoke = invokeClient) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const result = invoke(
      python,
      ['process-info', '--pid', String(pid)],
      { quiet: true, timeoutMs: 1_500 },
    )
    if (result.status === 0) return parseJsonOutput(result)
    if (attempt < 2) sleepSync(100)
  }
  return null
}

function normalizePathForComparison (value) {
  try {
    return path.resolve(String(value)).replaceAll('\\', '/').toLowerCase()
  } catch (_) {
    return String(value).replaceAll('\\', '/').toLowerCase()
  }
}

function supervisorIdentityMatches (record, processInfo, python, root = ROOT) {
  const expected = record?.process
  if (!expected || !processInfo) return false
  const selectedPythonIsLauncher = path.basename(python).toLowerCase() === 'py.exe'
  const command = Array.isArray(processInfo.command) ? processInfo.command : []
  const expectedCommand = Array.isArray(expected.command) ? expected.command : []
  return (
    Number(record.pid) === Number(expected.pid)
    && Number(processInfo.pid) === Number(expected.pid)
    && Math.abs(Number(expected.create_time) - Number(processInfo.create_time)) < 0.01
    && normalizePathForComparison(expected.executable) === normalizePathForComparison(processInfo.executable)
    && (selectedPythonIsLauncher || normalizePathForComparison(expected.executable) === normalizePathForComparison(python))
    && JSON.stringify(expectedCommand) === JSON.stringify(command)
    && command.includes('-m')
    && command.includes('app.lifecycle.supervisor')
    && command.includes('--serve')
    && normalizePathForComparison(expected.cwd || root) === normalizePathForComparison(processInfo.cwd)
  )
}

function quarantineControlRecord (controlRecord = CONTROL_RECORD) {
  if (!fs.existsSync(controlRecord)) return null
  const directory = path.dirname(controlRecord)
  const prefix = path.join(directory, 'lifecycle-control.stale.')
  let target = `${prefix}${Date.now()}.json`
  let suffix = 1
  while (fs.existsSync(target)) {
    target = `${prefix}${Date.now()}.${suffix}.json`
    suffix += 1
  }
  fs.renameSync(controlRecord, target)
  return target
}

function sleepSync (milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds)
}

function processIsAlive (pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error?.code === 'EPERM'
  }
}

function withControlLock (controlRecord, callback, timeoutMs = 15_000) {
  const lockPath = `${controlRecord}.lock`
  fs.mkdirSync(path.dirname(lockPath), { recursive: true })
  const deadline = Date.now() + timeoutMs
  let handle = null
  while (!handle && Date.now() < deadline) {
    try {
      handle = fs.openSync(lockPath, 'wx')
      fs.writeSync(handle, String(process.pid))
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error
      let ownerPid = null
      try { ownerPid = Number(fs.readFileSync(lockPath, 'utf8')) } catch (_) {}
      if (Number.isInteger(ownerPid) && ownerPid > 0 && !processIsAlive(ownerPid)) {
        try { fs.unlinkSync(lockPath) } catch (unlinkError) {
          if (unlinkError?.code !== 'ENOENT') throw unlinkError
        }
      } else {
        sleepSync(100)
      }
    }
  }
  if (handle === null) {
    throw new Error('control_start_in_progress: another lifecycle command is acquiring the control plane')
  }
  try {
    return callback()
  } finally {
    fs.closeSync(handle)
    try { fs.unlinkSync(lockPath) } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
  }
}

function startReplacement ({
  controlRecord,
  spawnSupervisor,
  wait,
  result,
}) {
  const staleRecord = quarantineControlRecord(controlRecord)
  try {
    spawnSupervisor()
    wait()
    return result
  } catch (error) {
    if (staleRecord && !fs.existsSync(controlRecord)) {
      fs.renameSync(staleRecord, controlRecord)
    }
    throw error
  }
}

function terminateSupervisor (pid) {
  process.kill(pid)
}

function waitForProcessExit (pid, timeoutMs = 5_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      process.kill(pid, 0)
    } catch (error) {
      if (error?.code === 'ESRCH') return true
      if (error?.code !== 'EPERM') throw error
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100)
  }
  return false
}

function recoverControl ({
  record,
  processInfo,
  identityMatches,
  terminate = terminateSupervisor,
  waitForExit = waitForProcessExit,
} = {}) {
  if (!record || !processInfo || !identityMatches) {
    throw new Error('control_owner_unverified: refusing to recover an unverified process')
  }
  const pid = Number(record.pid)
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new Error('control_owner_unverified: control record has no valid Supervisor PID')
  }
  terminate(pid)
  if (!waitForExit(pid)) {
    throw new Error(`control_recovery_timeout: Supervisor PID ${pid} did not exit`)
  }
  return { state: 'recovered', pid }
}

function startSupervisor (python) {
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
}

function ensureSupervisor (python, {
  controlRecord = CONTROL_RECORD,
  allowRecovery = false,
  invoke = invokeClient,
  inspect = inspectSupervisor,
  spawnSupervisor = startSupervisor,
  wait = waitForControl,
  terminate = terminateSupervisor,
  waitForExit = waitForProcessExit,
} = {}) {
  return withControlLock(controlRecord, () => {
    const record = readControlRecord(controlRecord)
    if (record) {
      const result = invoke(python, ['status'], { quiet: true, timeoutMs: 1_500 })
      if (result.status === 0) return { state: 'reusable' }

      const pid = Number(record.pid)
      const processInfo = Number.isInteger(pid) ? inspect(python, pid, invoke) : null
      const identityMatches = supervisorIdentityMatches(record, processInfo, python)
      const classification = classifyControlState({
        record,
        statusOk: false,
        processInfo,
        identityMatches,
      })

      if (classification.state === 'stale') {
        return startReplacement({
          controlRecord,
          spawnSupervisor: () => spawnSupervisor(python),
          wait: () => wait(python),
          result: classification,
        })
      }
      if (classification.state === 'unverified') {
        throw new Error(
          `control_owner_unverified: lifecycle PID ${record.pid} is alive but its identity does not match the recorded Supervisor`,
        )
      }
      if (allowRecovery) {
        const recovery = recoverControl({
          record,
          processInfo,
          identityMatches,
          terminate,
          waitForExit,
        })
        return startReplacement({
          controlRecord,
          spawnSupervisor: () => spawnSupervisor(python),
          wait: () => wait(python),
          result: recovery,
        })
      }
      throw new Error(
        `control_endpoint_unavailable: Lifecycle Supervisor (PID ${record.pid}) is alive but its control endpoint is unavailable. ` +
        'Use --recover-control only after confirming the process belongs to this workspace.',
      )
    }

    spawnSupervisor(python)
    wait(python)
    return { state: 'started' }
  })
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
  ensureSupervisor(python, { allowRecovery: argv.includes('--recover-control') })

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
  classifyControlState,
  controlTimeoutFor,
  computeBuildFingerprint,
  ensureFrontendBuild,
  ensureSupervisor,
  recoverControl,
  main,
  readRuntimeConfig,
  selectPython,
  npmInvocation,
}
