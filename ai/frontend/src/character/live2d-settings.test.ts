import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeLive2DPerformanceSettings,
  resolvePersistedLive2DModel,
  resolveLive2DRenderDpr,
} from './Live2DPerformanceSettings.ts'

test('caps high-DPI Live2D rendering without upscaling invalid values', () => {
  assert.equal(resolveLive2DRenderDpr(1.5), 1.5)
  assert.equal(resolveLive2DRenderDpr(2), 2)
  assert.equal(resolveLive2DRenderDpr(2.5), 2)
  assert.equal(resolveLive2DRenderDpr(1), 1)
  assert.equal(resolveLive2DRenderDpr('invalid'), 1)
  assert.equal(resolveLive2DRenderDpr(0.5), 0.75)
})

test('normalizes persisted Live2D performance settings safely', () => {
  assert.deepEqual(normalizeLive2DPerformanceSettings({}), {
    mode: 'enhanced',
    parameterGain: 1.3,
    bodyMotionGain: 1.08,
  })
  assert.deepEqual(normalizeLive2DPerformanceSettings({
    mode: 'unknown' as any,
    parameterGain: 9,
    bodyMotionGain: -1,
  }), {
    mode: 'enhanced',
    parameterGain: 2.2,
    bodyMotionGain: 0.6,
  })
  assert.deepEqual(normalizeLive2DPerformanceSettings({
    mode: 'legacy',
    parameterGain: 1.45,
    bodyMotionGain: 1.25,
  }), {
    mode: 'legacy',
    parameterGain: 1.45,
    bodyMotionGain: 1.25,
  })
})

test('restores a persisted model only when it is a usable identifier', () => {
  assert.equal(resolvePersistedLive2DModel({ live2dModel: 'hiyori_zh-Hans' }), 'hiyori_zh-Hans')
  assert.equal(resolvePersistedLive2DModel({ live2dModel: '  ' }), '')
  assert.equal(resolvePersistedLive2DModel({ live2dModel: 42 }), '')
})
