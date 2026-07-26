const assert = require('node:assert/strict')
const test = require('node:test')

const { canEnterCompanion } = require('./startup-policy.cjs')

test('startup console remains visible until every enabled capability is ready', () => {
  assert.equal(canEnterCompanion({ availability: 'BLOCKED' }), false)
  assert.equal(canEnterCompanion({ availability: 'TEXT_READY' }), false)
  assert.equal(canEnterCompanion({ availability: 'VOICE_READY' }), false)
  assert.equal(canEnterCompanion({ availability: 'FULL_READY' }), true)
})
