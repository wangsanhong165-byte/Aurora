import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  normalizeAvatarViewport,
  type AvatarCapabilityProfile,
} from './AvatarCapabilityProfile.ts'
import { AvatarParameterResolver } from './AvatarParameterResolver.ts'
import { logicalFaceFromFACS } from './performance/FACSState.ts'
import { computeDrawableBounds } from './live2d/viewport.ts'

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

test('resolver omits channels explicitly unsupported by the model', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile({
    capabilities: { headControl: true, bodyControl: false },
  }))

  assert.deepEqual(resolver.values({ 'head.x': 2, 'body.x': 3 }), {
    ParamAngleX: 2,
  })
})

test('face expression channels are independent from gaze capability', () => {
  const resolver = new AvatarParameterResolver()
  resolver.setProfile(profile({
    capabilities: { gazeControl: false, browControl: true },
    bindings: {
      'eye.x': 'ParamEyeBallX',
      'eye.left.smile': { target: 'ParamEyeLSmile', min: 0, max: 1 },
      'brow.left.y': { target: 'ParamBrowLY', min: -1, max: 1 },
    },
  }))

  assert.deepEqual(resolver.values({
    'eye.x': 0.5,
    'eye.left.smile': 0.5,
    'brow.left.y': 0.5,
  }), {
    ParamEyeLSmile: 0.5,
    ParamBrowLY: 0.5,
  })
})

test('Design_genius_White routes body motion into its physical body inputs', () => {
  const profile = JSON.parse(readFileSync(
    new URL('../../../config/avatar_profiles/Design_genius_White.json', import.meta.url),
    'utf8',
  )) as { bindings: Record<string, string | { target: string }> }

  const target = (logical: string) => {
    const binding = profile.bindings[logical]
    return typeof binding === 'string' ? binding : binding?.target
  }

  assert.deepEqual(
    ['body.x', 'body.y', 'body.z'].map(target),
    ['ParamBodyAngleX', 'ParamBodyAngleY', 'ParamBodyAngleZ'],
  )
})

test('shirone profile recruits torso rotation and its segmented cat-tail without controlling limbs', () => {
  const profile = JSON.parse(readFileSync(
    new URL('../../../config/avatar_profiles/shirone.json', import.meta.url),
    'utf8',
  )) as AvatarCapabilityProfile

  assert.equal(profile.bindings['body.z'], 'ParamBodyAngleZ')
  assert.equal(
    typeof profile.bindings['tail.z'] === 'string'
      ? profile.bindings['tail.z']
      : profile.bindings['tail.z']?.target,
    'Param_Angle_Rotation_1_ArtMesh572',
  )
  for (let index = 1; index <= 15; index += 1) {
    const key = `tail.segment${String(index).padStart(2, '0')}`
    const binding = profile.bindings[key]
    assert.equal(typeof binding === 'string' ? binding : binding?.target,
      `Param_Angle_Rotation_${index}_ArtMesh571`)
  }
  assert.equal(Object.keys(profile.bindings).some(key => key.startsWith('arm.')), false)
})

test('Design_genius_White does not advertise body rotation as an arm wave', () => {
  const profile = JSON.parse(readFileSync(
    new URL('../../../config/avatar_profiles/Design_genius_White.json', import.meta.url),
    'utf8',
  )) as AvatarCapabilityProfile

  assert.equal(profile.motions.includes('arm_wave'), false)
  assert.deepEqual(profile.semanticMotionMap, {
    greet: 'tilt',
    wave: 'sway',
    agree: 'nod',
    excited: 'sway',
  })
  assert.equal(profile.motions.includes('tail_sway'), false)
})

test('Design_genius_White behavior config cannot reintroduce the ghosting arm pose', () => {
  const configs = JSON.parse(readFileSync(
    new URL('../../../config/live2d_models.json', import.meta.url),
    'utf8',
  )) as Record<string, {
    emotion_map: Record<string, string>
    behavior_map: Record<string, { motion?: string }>
    accessories: Record<string, string>
  }>
  const config = configs.Design_genius_White

  assert.equal(Object.values(config.emotion_map).includes('zs11'), false)
  assert.equal(Object.values(config.accessories).includes('14'), false)
  assert.equal(Object.values(config.accessories).includes('144'), false)
  const controllerSource = readFileSync(new URL('./controllers.ts', import.meta.url), 'utf8')
  for (const unsafeExpression of ['14', '144', '中指', '中指2']) {
    assert.ok(controllerSource.includes(`expression !== '${unsafeExpression}'`))
  }
  assert.deepEqual({
    greet: config.behavior_map.greet.motion,
    wave: config.behavior_map.wave.motion,
    agree: config.behavior_map.agree.motion,
    excited: config.behavior_map.excited.motion,
  }, {
    greet: 'tilt',
    wave: 'sway',
    agree: 'nod',
    excited: 'sway',
  })
})

test('FACS face mapping stays subtle and avoids the model-specific cheek overlay', () => {
  assert.deepEqual(logicalFaceFromFACS({
    browInnerUp: 0.4,
    browOuterUp: 0.2,
    eyeSquint: 0.5,
    mouthSmile: 0.6,
    mouthPucker: 0.1,
  }), {
    'brow.left.y': 0.344,
    'brow.right.y': 0.344,
    'eye.left.smile': 0.5,
    'eye.right.smile': 0.5,
    'mouth.form': 0.5,
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

test('model framing centers drawable artwork instead of transparent canvas margins', () => {
  assert.deepEqual(computeDrawableBounds([
    [-8, -2, -4, -2, -4, 6, -8, 6],
    [2, -1, 6, -1, 6, 3, 2, 3],
  ]), {
    left: -8,
    right: 6,
    top: -2,
    bottom: 6,
    centerX: -1,
    centerY: 2,
  })
  assert.equal(computeDrawableBounds([]), null)
})
