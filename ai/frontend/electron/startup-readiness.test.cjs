const assert = require('node:assert/strict')
const test = require('node:test')

const { serviceUrl, waitForUrl } = require('./startup-readiness.cjs')

test('serviceUrl resolves the endpoint returned by the lifecycle supervisor', () => {
  const status = {
    services: [
      { id: 'bridge', host: '127.0.0.1', port: 19306 },
      { id: 'frontend', host: '127.0.0.1', port: 19573 },
    ],
  }

  assert.equal(serviceUrl(status, 'bridge'), 'http://127.0.0.1:19306')
  assert.equal(serviceUrl(status, 'frontend'), 'http://127.0.0.1:19573')
  assert.equal(serviceUrl(status, 'missing'), null)
})

test('waitForUrl waits through a refused connection and resolves when the app is ready', async () => {
  const probes = []

  const result = await waitForUrl('http://127.0.0.1:19306/', {
    intervalMs: 5,
    timeoutMs: 100,
    probe: async url => {
      probes.push(url)
      return probes.length >= 3
    },
  })

  assert.equal(result, true)
  assert.ok(probes.length >= 1)
})

test('waitForUrl returns false after the bounded degraded-start window', async () => {
  const result = await waitForUrl('http://127.0.0.1:19306/', {
    intervalMs: 1,
    timeoutMs: 5,
    probe: async () => false,
  })

  assert.equal(result, false)
})
