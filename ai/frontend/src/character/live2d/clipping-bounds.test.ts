import assert from 'node:assert/strict'
import test from 'node:test'
import {
  createEmptyClippingBounds,
  includeClippingBounds,
} from './framework/rendering/clipping-bounds.ts'

test('clipping bounds preserve a negative maximum coordinate', () => {
  const bounds = createEmptyClippingBounds()
  includeClippingBounds(bounds, -0.1087, 0.4812, -0.0318, 0.6609)

  assert.ok(Math.abs(bounds.minX - (-0.1087)) < 1e-6)
  assert.ok(Math.abs(bounds.minY - 0.4812) < 1e-6)
  assert.ok(Math.abs((bounds.maxX - bounds.minX) - 0.0769) < 1e-6)
  assert.ok(Math.abs((bounds.maxY - bounds.minY) - 0.1797) < 1e-6)
})

test('clipping bounds preserve a fully negative vertical range', () => {
  const bounds = createEmptyClippingBounds()
  includeClippingBounds(bounds, 0.0656991, -0.1466682, 0.1477409, -0.0313244)

  assert.ok(Math.abs(bounds.minX - 0.0656991) < 1e-6)
  assert.ok(Math.abs(bounds.minY - (-0.1466682)) < 1e-6)
  assert.ok(Math.abs((bounds.maxX - bounds.minX) - 0.0820418) < 1e-6)
  assert.ok(Math.abs((bounds.maxY - bounds.minY) - 0.1153438) < 1e-6)
})
