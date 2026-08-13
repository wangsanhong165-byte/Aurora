import assert from 'node:assert/strict'
import test from 'node:test'
import {
  countClippingMaskGroups,
  requiredMaskRenderTextureCount,
} from './framework/rendering/mask-buffer-layout.ts'

test('counts repeated mask sets as one clipping group', () => {
  const masks = [
    new Int32Array([3, 7]),
    new Int32Array([7, 3]),
    new Int32Array([11]),
    new Int32Array(),
  ]
  const counts = new Int32Array([2, 2, 1, 0])

  assert.equal(countClippingMaskGroups(masks, counts), 2)
})

test('allocates enough render textures for a 57-group model', () => {
  assert.equal(requiredMaskRenderTextureCount(36), 1)
  assert.equal(requiredMaskRenderTextureCount(37), 2)
  assert.equal(requiredMaskRenderTextureCount(57), 2)
  assert.equal(requiredMaskRenderTextureCount(65), 3)
})
