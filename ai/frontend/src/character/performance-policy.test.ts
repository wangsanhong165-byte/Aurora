import assert from 'node:assert/strict'
import test from 'node:test'

import { isPerFrameGazeLoggingEnabled } from './performance-policy.ts'
import { CharacterPerformancePolicy } from './CharacterPerformancePolicy.ts'
import type { AvatarCapabilityProfile } from './AvatarCapabilityProfile.ts'
import type { CharacterBehaviorConfig } from './CharacterBehaviorResolver.ts'

test('per-frame gaze logging is disabled unless diagnostics explicitly enable it', () => {
  assert.equal(isPerFrameGazeLoggingEnabled(undefined), false)
  assert.equal(isPerFrameGazeLoggingEnabled(false), false)
  assert.equal(isPerFrameGazeLoggingEnabled(true), true)
})

test('Design_genius_White semantics use honest executable gestures', () => {
  const profile: AvatarCapabilityProfile = {
    model: 'Design_genius_White',
    expressions: [],
    motions: ['tilt', 'nod', 'sway'],
    sequences: ['greet'],
    parameters: {},
    bindings: {},
    semanticMotionMap: { greet: 'tilt', wave: 'sway', agree: 'nod' },
  }
  const config: CharacterBehaviorConfig = {}
  const plan = new CharacterPerformancePolicy().evaluate(
    { emotion: 'happy', behavior: 'greet', intensity: 0.8, energy: 0.7 },
    { expression: 'happy', expressionIntensity: 0.8, motion: 'wave', motionIntensity: 0.7, suppressIdle: false },
    config,
    profile,
  )

  assert.equal(plan.motion, 'tilt')

  const touchPlan = new CharacterPerformancePolicy().evaluate(
    { emotion: 'happy', behavior: 'agree', intensity: 0.5, energy: 0.4 },
    { expression: 'happy', expressionIntensity: 0.5, motion: 'nod', motionIntensity: 0.4, suppressIdle: false },
    config,
    profile,
  )
  assert.equal(touchPlan.motion, 'nod')
})

test('direct interactions always deliver their mapped reaction motion', () => {
  const profile: AvatarCapabilityProfile = {
    model: 'Design_genius_White',
    expressions: [],
    motions: ['nod'],
    sequences: [],
    parameters: {},
    bindings: {},
    semanticMotionMap: { agree: 'nod' },
  }
  const plan = new CharacterPerformancePolicy().evaluate(
    {
      emotion: 'happy',
      behavior: 'agree',
      intensity: 0.42,
      energy: 0.4,
      contextTags: ['interaction', 'touch'],
    },
    { expression: 'happy', expressionIntensity: 0.42, motion: 'nod', motionIntensity: 0.4, suppressIdle: false },
    {},
    profile,
  )

  assert.equal(plan.motion, 'nod')
  assert.equal(plan.motionProbability, 1)
})
