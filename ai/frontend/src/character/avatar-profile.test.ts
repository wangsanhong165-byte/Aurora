import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeAvatarViewport,
  type AvatarCapabilityProfile,
} from './AvatarCapabilityProfile.ts'
import { AvatarParameterResolver } from './AvatarParameterResolver.ts'
import { inspectIdleMotionChannels } from './live2d/IdleMotionInspection.ts'

function profile(
  overrides: Partial<AvatarCapabilityProfile> = {},
): AvatarCapabilityProfile {
  return {
    model: 'test',
    expressions: [],
    motions: [],
    parameters: {},
    bindings: {
      'head.x': { target: 'ParamAngleX', min: -8, max: 8 },
      'body.x': 'ParamBodyAngleX',
      'mouth.open': { target: 'ParamMouthOpenY', min: 0, max: 0.7 },
    },
    ...overrides,
  }
}

test('resolver clamps output to model binding range', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile())

  assert.deepEqual(resolver.values({ 'head.x': 30, 'mouth.open': 1 }), {
    ParamAngleX: 8,
    ParamMouthOpenY: 0.7,
  })
})

test('idle inspection rejects effect-only motion without head body or breath channels', () => {
  const report = inspectIdleMotionChannels({
    Curves: [
      { Target: 'Parameter', Id: 'Param38' },
      { Target: 'Parameter', Id: 'Param39' },
    ],
  })
  assert.equal(report.naturalChannelCount, 0)
  assert.equal(report.valid, false)
})

test('resolver omits channels explicitly unsupported by the model', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile({
    capabilities: { headControl: true, bodyControl: false },
  }))

  assert.deepEqual(resolver.values({ 'head.x': 2, 'body.x': 3 }), {
    ParamAngleX: 2,
  })
})

test('motion parameter resolution protects lip-sync ownership', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile())

  assert.deepEqual(
    resolver.resolveMotionParameters({ 'head.x': 3, 'mouth.open': 0.6 }),
    { ParamAngleX: 3 },
  )
  assert.equal(resolver.isProtectedMotionTarget('ParamMouthOpenY'), true)
  assert.equal(resolver.isProtectedMotionTarget('ParamAngleX'), false)
})

test('resolver exposes per-model lip-sync calibration with safe defaults', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile({
    lipSync: {
      max: 0.64,
      inputGain: 5.2,
      noiseGate: 0.02,
      attackMs: 45,
      releaseMs: 135,
      peakBoost: 0.2,
    },
  }))

  assert.deepEqual(resolver.getLipSyncConfig(), {
    min: 0,
    max: 0.64,
    inputGain: 5.2,
    noiseGate: 0.02,
    attackMs: 45,
    releaseMs: 135,
    peakBoost: 0.2,
  })
})

test('model viewport framing is bounded and defaults to a centered view', () => {
  assert.deepEqual(normalizeAvatarViewport(undefined), { x: 0, y: 0, scale: 1 })
  assert.deepEqual(normalizeAvatarViewport({ x: 4, y: -4, scale: 0.1 }), {
    x: 1.5,
    y: -1.5,
    scale: 0.35,
  })
})
