const assert = require('node:assert/strict')
const test = require('node:test')

const { ProcessManager, requestTimeoutFor } = require('./process-manager.cjs')

test('startup commands keep the lifecycle client alive through model warmup', () => {
  assert.equal(requestTimeoutFor('start'), 480_000)
  assert.equal(requestTimeoutFor('restart'), 480_000)
  assert.equal(requestTimeoutFor('status'), 30_000)
})

test('startAll passes the long startup timeout to the lifecycle client', () => {
  const manager = new ProcessManager()
  const calls = []
  manager._request = (...args) => {
    calls.push(args)
    return Promise.resolve({ availability: 'BLOCKED', services: [], capabilities: [] })
  }

  manager.startAll()

  assert.deepEqual(calls, [
    ['start', { profile: 'electron' }, 480_000],
  ])
})

test('startAll resolves only after the lifecycle start response is ready', async () => {
  const manager = new ProcessManager()
  let resolveRequest
  manager._request = () => new Promise(resolve => {
    resolveRequest = resolve
  })

  let settled = false
  const pending = manager.startAll().then(status => {
    settled = true
    return status
  })

  await Promise.resolve()
  assert.equal(settled, false)
  resolveRequest({ availability: 'FULL_READY', services: [], capabilities: [] })
  assert.equal((await pending).availability, 'FULL_READY')
})

test('concurrent refresh calls share one lifecycle status request', async () => {
  const manager = new ProcessManager()
  let requestCount = 0
  let completeRequest
  const pendingStatus = new Promise(resolve => {
    completeRequest = resolve
  })

  manager._request = async command => {
    assert.equal(command, 'status')
    requestCount += 1
    return pendingStatus
  }

  const first = manager.refresh()
  const second = manager.refresh()

  assert.equal(requestCount, 1)
  completeRequest({ availability: 'TEXT_READY', services: [], capabilities: [] })
  const [firstStatus, secondStatus] = await Promise.all([first, second])

  assert.equal(firstStatus.availability, 'TEXT_READY')
  assert.equal(secondStatus.availability, 'TEXT_READY')
})

test('concurrent restart calls share one lifecycle restart request', async () => {
  const manager = new ProcessManager()
  let requestCount = 0
  let completeRequest
  manager._request = command => {
    assert.equal(command, 'restart')
    requestCount += 1
    return new Promise(resolve => { completeRequest = resolve })
  }

  const first = manager.restartAll()
  const second = manager.restartAll()

  assert.equal(requestCount, 1)
  assert.equal(first, second)
  completeRequest({ availability: 'FULL_READY', services: [], capabilities: [] })
  assert.equal((await first).availability, 'FULL_READY')
})

test('refresh returns the cached status inside the refresh interval', async () => {
  const manager = new ProcessManager()
  let requestCount = 0
  manager._request = async () => {
    requestCount += 1
    return { availability: 'TEXT_READY', services: [], capabilities: [] }
  }

  await manager.refresh()
  await manager.refresh()

  assert.equal(requestCount, 1)
})

test('forced refresh starts a new status request inside the refresh interval', async () => {
  const manager = new ProcessManager()
  let requestCount = 0
  manager._request = async () => {
    requestCount += 1
    return { availability: 'TEXT_READY', services: [], capabilities: [] }
  }

  await manager.refresh()
  await manager.refresh(true)

  assert.equal(requestCount, 2)
})

test('application shutdown stops all registered services even when reusing a launch', async () => {
  const manager = new ProcessManager()
  const commands = []
  manager.ownsLaunch = false
  manager._request = async (command, extra) => {
    commands.push([command, extra])
    return { availability: 'BLOCKED', services: [], capabilities: [] }
  }

  await manager.shutdownAll()

  assert.deepEqual(commands, [['shutdown', undefined]])
})
