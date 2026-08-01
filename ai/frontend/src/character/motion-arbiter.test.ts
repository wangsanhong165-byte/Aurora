import assert from 'node:assert/strict'
import test from 'node:test'

import { MotionArbiter, type MotionPreset } from './MotionArbiter.ts'

const presets: Record<string, MotionPreset> = {
  nod: {
    name: 'nod',
    duration: 500,
    keyframes: [
      { time: 0, parameter: 'head.y', value: 0 },
      { time: 250, parameter: 'head.y', value: 4 },
      { time: 500, parameter: 'head.y', value: 0 },
    ],
  },
  sway: {
    name: 'sway',
    duration: 800,
    keyframes: [
      { time: 0, parameter: 'body.x', value: 0 },
      { time: 400, parameter: 'body.x', value: 3 },
      { time: 800, parameter: 'body.x', value: 0 },
    ],
  },
}

test('motion requests coexist when their control channels do not overlap', () => {
  let now = 0
  const arbiter = new MotionArbiter(() => now)
  arbiter.setPresets(presets)

  assert.equal(arbiter.request({
    name: 'nod', owner: 'ai:head', source: 'ai', priority: 40,
    channels: ['head'], turnId: 'turn-1',
  }), true)
  assert.equal(arbiter.request({
    name: 'sway', owner: 'system:body', source: 'system', priority: 20,
    channels: ['body'], turnId: 'turn-1',
  }), true)

  now = 250
  const contributions = arbiter.update(0)
  assert.deepEqual(
    new Set(contributions.map(item => item.logicalParameter)),
    new Set(['head.y', 'body.x']),
  )
})

test('higher priority request preempts only overlapping channels', () => {
  const arbiter = new MotionArbiter(() => 0)
  arbiter.setPresets(presets)
  arbiter.request({
    name: 'nod', owner: 'ai:head', source: 'ai', priority: 40,
    channels: ['head'], turnId: 'turn-1',
  })
  arbiter.request({
    name: 'sway', owner: 'system:body', source: 'system', priority: 20,
    channels: ['body'], turnId: 'turn-1',
  })

  assert.equal(arbiter.request({
    name: 'nod', owner: 'idle:head', source: 'idle', priority: 10,
    channels: ['head'], turnId: 'turn-1',
  }), false)
  assert.equal(arbiter.request({
    name: 'nod', owner: 'ui:head', source: 'system', priority: 90,
    channels: ['head'], turnId: 'turn-2',
  }), true)

  const owners = arbiter.getDebugState().activeRequests.map(item => item.owner)
  assert.deepEqual(new Set(owners), new Set(['system:body', 'ui:head']))
})

test('turn cancellation and timeout release motion ownership', () => {
  let now = 0
  const arbiter = new MotionArbiter(() => now)
  arbiter.setPresets(presets)
  arbiter.request({
    name: 'nod', owner: 'ai:head', source: 'ai', priority: 40,
    channels: ['head'], turnId: 'turn-1', timeoutMs: 100,
  })
  arbiter.request({
    name: 'sway', owner: 'system:body', source: 'system', priority: 20,
    channels: ['body'], turnId: 'turn-2',
  })

  assert.equal(arbiter.cancelTurn('turn-2'), 1)
  now = 101
  assert.deepEqual(arbiter.update(0), [])
  assert.equal(arbiter.isPlaying(), false)
})

test('LLM motion preempts the lower-priority speaking background', () => {
  const arbiter = new MotionArbiter(() => 0)
  arbiter.setPresets(presets)
  assert.equal(arbiter.request({
    name: 'nod', owner: 'state:speaking', source: 'system', priority: 35,
    channels: ['head', 'body'], turnId: 'turn-1',
  }), true)
  assert.equal(arbiter.request({
    name: 'sway', owner: 'intent-plan:turn-1', source: 'ai', priority: 52,
    channels: ['full'], turnId: 'turn-1',
  }), true)
  assert.deepEqual(
    arbiter.getDebugState().activeRequests.map(item => item.owner),
    ['intent-plan:turn-1'],
  )
})
