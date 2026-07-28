const assert = require('node:assert/strict')
const test = require('node:test')

const { ProcessManager } = require('./process-manager.cjs')

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

test('refresh starts a new status request after the previous one settles', async () => {
  const manager = new ProcessManager()
  let requestCount = 0
  manager._request = async () => {
    requestCount += 1
    return { availability: 'TEXT_READY', services: [], capabilities: [] }
  }

  await manager.refresh()
  await manager.refresh()

  assert.equal(requestCount, 2)
})
