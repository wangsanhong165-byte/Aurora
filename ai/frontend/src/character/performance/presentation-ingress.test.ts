import assert from 'node:assert/strict'
import test from 'node:test'

import { PresentationIngress } from './PresentationIngress.ts'

test('higher-authority interaction temporarily blocks only its claimed channels', () => {
  let now = 100
  const ingress = new PresentationIngress(() => now)
  ingress.submit({
    source: 'interaction', owner: 'touch', leaseMs: 500,
    channels: ['expression', 'attention'], intent: { emotion: 'happy', attention: 'user' },
  })

  const llm = ingress.submit({
    source: 'llm', owner: 'turn:1', turnId: '1', leaseMs: 1000,
    intent: { emotion: 'sad', behavior: 'speak', motionPlan: { durationMs: 600, steps: [] } },
  })

  assert.deepEqual([...llm!.channels], ['motion', 'activity'])
  now = 601
  const afterExpiry = ingress.submit({
    source: 'llm', owner: 'turn:1', turnId: '1', intent: { emotion: 'sad' },
  })
  assert.deepEqual([...afterExpiry!.channels], ['expression', 'motion', 'attention', 'activity'])
})

test('releasing a completed turn prevents stale ownership leaking forward', () => {
  const ingress = new PresentationIngress(() => 100)
  ingress.submit({ source: 'lifecycle', owner: 'turn:old', turnId: 'old', leaseMs: 5000, intent: {} })
  ingress.releaseTurn('old')

  const next = ingress.submit({ source: 'llm', owner: 'turn:new', turnId: 'new', intent: {} })
  assert.equal(next!.channels.size, 4)
})
