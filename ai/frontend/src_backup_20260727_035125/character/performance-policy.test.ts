import assert from 'node:assert/strict'
import test from 'node:test'

import { isPerFrameGazeLoggingEnabled } from './performance-policy.ts'

test('per-frame gaze logging is disabled unless diagnostics explicitly enable it', () => {
  assert.equal(isPerFrameGazeLoggingEnabled(undefined), false)
  assert.equal(isPerFrameGazeLoggingEnabled(false), false)
  assert.equal(isPerFrameGazeLoggingEnabled(true), true)
})
