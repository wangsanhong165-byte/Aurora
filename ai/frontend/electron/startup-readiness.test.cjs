const assert = require('node:assert/strict')
const test = require('node:test')

const { waitForUrl } = require('./startup-readiness.cjs')

test('waitForUrl waits through a refused connection and resolves when the app is ready', async () => {
  const probes = []

  const result = await waitForUrl('http://127.0.0.1:9528/', {
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
  const result = await waitForUrl('http://127.0.0.1:9528/', {
    intervalMs: 1,
    timeoutMs: 5,
    probe: async () => false,
  })

  assert.equal(result, false)
})
