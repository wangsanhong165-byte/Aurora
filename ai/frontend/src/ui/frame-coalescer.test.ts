import assert from 'node:assert/strict'
import test from 'node:test'

import { createFrameCoalescer } from './frame-coalescer.ts'

test('multiple updates in one frame commit only the latest value', () => {
  let scheduled: (() => void) | null = null
  const committed: number[] = []
  const coalescer = createFrameCoalescer<number>(
    (value) => committed.push(value),
    (callback) => {
      scheduled = callback
      return 1
    },
    () => {},
  )

  coalescer.schedule(360)
  coalescer.schedule(380)
  coalescer.schedule(420)

  assert.deepEqual(committed, [])
  assert.ok(scheduled)
  ;(scheduled as () => void)()
  assert.deepEqual(committed, [420])
})

test('cancelling a scheduled frame prevents its commit', () => {
  let scheduled: (() => void) | null = null
  let cancelled = 0
  const committed: number[] = []
  const coalescer = createFrameCoalescer<number>(
    (value) => committed.push(value),
    (callback) => {
      scheduled = callback
      return 7
    },
    (id) => { cancelled = id },
  )

  coalescer.schedule(400)
  coalescer.cancel()
  ;(scheduled as unknown as () => void)()

  assert.equal(cancelled, 7)
  assert.deepEqual(committed, [])
})
