const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const { classifyControlState, ensureSupervisor, recoverControl } = require('./soulctl.cjs')

test('healthy endpoint is reusable', () => {
  assert.deepEqual(
    classifyControlState({ record: { pid: 10 }, statusOk: true }),
    { state: 'reusable' },
  )
})

test('exited supervisor is stale', () => {
  assert.deepEqual(
    classifyControlState({
      record: { pid: 10 },
      statusOk: false,
      processInfo: null,
    }),
    { state: 'stale' },
  )
})

test('inaccessible unverified supervisor is not safe to kill', () => {
  assert.deepEqual(
    classifyControlState({
      record: { pid: 10, process: { pid: 10 } },
      statusOk: false,
      processInfo: { pid: 10 },
      identityMatches: false,
    }),
    { state: 'unverified' },
  )
})

test('verified live supervisor is recoverable only explicitly', () => {
  assert.deepEqual(
    classifyControlState({
      record: { pid: 10, process: { pid: 10 } },
      statusOk: false,
      processInfo: { pid: 10 },
      identityMatches: true,
    }),
    { state: 'recoverable' },
  )
})

test('ensureSupervisor does not replace an unverified live process', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'soulctl-test-'))
  const controlRecord = path.join(directory, 'lifecycle-control.json')
  fs.writeFileSync(controlRecord, JSON.stringify({
    pid: 10,
    process: {
      pid: 10,
      create_time: 100,
      executable: 'D:/conda/python.exe',
      command: ['python.exe', '-m', 'app.lifecycle.supervisor', '--serve'],
      cwd: directory,
    },
  }))
  let spawned = 0

  assert.throws(() => ensureSupervisor('D:/conda/python.exe', {
    controlRecord,
    invoke: () => ({ status: 1, stdout: '' }),
    inspect: () => ({
      pid: 10,
      create_time: 100,
      executable: 'C:/other/python.exe',
      command: ['python.exe', '-m', 'other'],
      cwd: directory,
    }),
    spawnSupervisor: () => { spawned += 1 },
    wait: () => {},
  }), /control_owner_unverified/)

  assert.equal(spawned, 0)
  fs.rmSync(directory, { recursive: true, force: true })
})

test('ensureSupervisor quarantines a record for an exited process', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'soulctl-test-'))
  const controlRecord = path.join(directory, 'lifecycle-control.json')
  fs.writeFileSync(controlRecord, JSON.stringify({ pid: 10 }))
  let spawned = 0

  ensureSupervisor('D:/conda/python.exe', {
    controlRecord,
    invoke: () => ({ status: 1, stdout: '' }),
    inspect: () => null,
    spawnSupervisor: () => { spawned += 1 },
    wait: () => {},
  })

  assert.equal(spawned, 1)
  assert.equal(fs.existsSync(controlRecord), false)
  assert.equal(
    fs.readdirSync(directory).some(name => name.startsWith('lifecycle-control.stale.')),
    true,
  )
  fs.rmSync(directory, { recursive: true, force: true })
})

test('recover-control terminates only a verified supervisor', () => {
  const calls = []
  const result = recoverControl({
    record: { pid: 10, process: { pid: 10 } },
    processInfo: { pid: 10 },
    identityMatches: true,
    terminate: pid => calls.push(pid),
    waitForExit: () => true,
  })

  assert.equal(result.state, 'recovered')
  assert.deepEqual(calls, [10])
})

test('recover-control refuses an unverified process', () => {
  assert.throws(
    () => recoverControl({
      record: { pid: 10 },
      processInfo: { pid: 10 },
      identityMatches: false,
      terminate: () => { throw new Error('must not terminate') },
    }),
    /control_owner_unverified/,
  )
})

test('ensureSupervisor recovers a verified control owner only when requested', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'soulctl-test-'))
  const controlRecord = path.join(directory, 'lifecycle-control.json')
  const snapshot = {
    pid: 10,
    create_time: 100,
    executable: 'D:/conda/python.exe',
    command: ['python.exe', '-m', 'app.lifecycle.supervisor', '--serve'],
    cwd: process.cwd(),
  }
  fs.writeFileSync(controlRecord, JSON.stringify({ pid: 10, process: snapshot }))
  const calls = []

  ensureSupervisor('D:/conda/python.exe', {
    controlRecord,
    allowRecovery: true,
    invoke: () => ({ status: 1, stdout: '' }),
    inspect: () => snapshot,
    terminate: pid => calls.push(['terminate', pid]),
    waitForExit: () => true,
    spawnSupervisor: () => calls.push(['spawn']),
    wait: () => calls.push(['wait']),
  })

  assert.deepEqual(calls, [['terminate', 10], ['spawn'], ['wait']])
  assert.equal(fs.existsSync(controlRecord), false)
  assert.equal(
    fs.readdirSync(directory).some(name => name.startsWith('lifecycle-control.stale.')),
    true,
  )
  fs.rmSync(directory, { recursive: true, force: true })
})
