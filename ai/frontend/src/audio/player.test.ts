import assert from 'node:assert/strict'
import test from 'node:test'

import { AudioPlaybackQueue } from './player.ts'

test('audio queue emits contiguous sequence order for the active turn', () => {
  const queue = new AudioPlaybackQueue()
  queue.beginTurn('turn-1', 0)

  assert.equal(queue.push({ audio: 'two', format: 'wav', turnId: 'turn-1', sequence: 2 }), true)
  assert.deepEqual(queue.drainReady(), [])
  assert.equal(queue.push({ audio: 'zero', format: 'wav', turnId: 'turn-1', sequence: 0 }), true)
  assert.deepEqual(queue.drainReady().map(item => item.sequence), [0])
  assert.equal(queue.push({ audio: 'one', format: 'wav', turnId: 'turn-1', sequence: 1 }), true)
  assert.deepEqual(queue.drainReady().map(item => item.sequence), [1, 2])
})

test('audio queue rejects stale and duplicate turn audio', () => {
  const queue = new AudioPlaybackQueue()
  queue.beginTurn('turn-new', 4)

  assert.equal(queue.push({ audio: 'stale', format: 'wav', turnId: 'turn-old', sequence: 4 }), false)
  assert.equal(queue.push({ audio: 'current', format: 'wav', turnId: 'turn-new', sequence: 4 }), true)
  assert.equal(queue.push({ audio: 'duplicate', format: 'wav', turnId: 'turn-new', sequence: 4 }), false)
  assert.deepEqual(queue.drainReady().map(item => item.audio), ['current'])
})

test('stopping one turn does not cancel a newer owner', () => {
  const queue = new AudioPlaybackQueue()
  queue.beginTurn('turn-new', 0)

  assert.equal(queue.stopTurn('turn-old'), false)
  assert.equal(queue.activeTurnId, 'turn-new')
  assert.equal(queue.stopTurn('turn-new'), true)
  assert.equal(queue.activeTurnId, null)
})
