import assert from 'node:assert/strict'
import test from 'node:test'

import {
  compileMotionAction,
  compileMotionPlan,
  isMotionPrimitiveSupported,
  normalizeMotionAction,
  unsupportedMotionPrimitives,
  validateMotionPlan,
} from './MotionAction.ts'

test('motion plan rejects renderer parameters and unknown primitives', () => {
  const result = validateMotionPlan({
    durationMs: 1200,
    steps: [
      { atMs: 0, durationMs: 500, primitive: 'nod', intensity: 0.7 },
      { atMs: 100, durationMs: 400, primitive: 'ParamAngleX', intensity: 1 },
    ],
    keyframes: [{ parameter: 'mouth.open', time: 0, value: 1 }],
  })

  assert.equal(result.ok, false)
  assert.match(result.errors.join(' '), /primitive|keyframes|mouth|renderer/i)
})

test('normalizes an authored action and compiles primitives to safe logical keyframes', () => {
  const action = normalizeMotionAction({
    version: 1,
    id: 'gentle_agree',
    name: 'Gentle Agree',
    durationMs: 1400,
    steps: [
      { atMs: 0, durationMs: 700, primitive: 'lean_forward', intensity: 0.25 },
      { atMs: 350, durationMs: 650, primitive: 'nod', intensity: 0.6 },
    ],
  })

  assert.equal(action.id, 'gentle_agree')
  assert.equal(action.steps.length, 2)
  const preset = compileMotionAction(action)
  assert.equal(preset.name, 'gentle_agree')
  assert.equal(preset.duration, 1400)
  assert.ok(preset.keyframes.some(frame => frame.parameter === 'body.y'))
  assert.ok(preset.keyframes.some(frame => frame.parameter === 'head.y'))
  assert.equal(preset.keyframes.some(frame => frame.parameter.startsWith('mouth.')), false)
  assert.equal(preset.keyframes.every(frame => frame.time >= 0 && frame.time <= 1400), true)
})

test('compiles the model-specific arm and tail primitives through logical bindings', () => {
  const action = normalizeMotionAction({
    version: 1,
    id: 'model_gesture_pair',
    name: 'Model Gesture Pair',
    durationMs: 1600,
    steps: [
      { atMs: 0, durationMs: 800, primitive: 'arm_wave', intensity: 0.8 },
      { atMs: 800, durationMs: 800, primitive: 'tail_sway', intensity: 0.7 },
    ],
  })

  const preset = compileMotionAction(action)
  assert.ok(preset.keyframes.some(frame => frame.parameter === 'body.z'))
  assert.ok(preset.keyframes.some(frame => frame.parameter === 'breath'))
  assert.equal(preset.keyframes.every(frame => frame.time >= 0 && frame.time <= 1600), true)
})

test('motion plans are bounded in duration, step count, and intensity', () => {
  const result = validateMotionPlan({
    durationMs: 99_000,
    steps: Array.from({ length: 20 }, (_, index) => ({
      atMs: index * 100,
      durationMs: 100,
      primitive: 'nod',
      intensity: 8,
    })),
  })

  assert.equal(result.ok, false)
  assert.match(result.errors.join(' '), /duration|steps|intensity/i)
})

test('model-authored appendage primitives require an explicit capability', () => {
  assert.equal(isMotionPrimitiveSupported('nod', []), true)
  assert.equal(isMotionPrimitiveSupported('arm_wave', ['tail_sway']), false)
  assert.equal(isMotionPrimitiveSupported('tail_sway', ['tail_sway']), true)

  const action = normalizeMotionAction({
    version: 1,
    id: 'old_fake_wave',
    name: 'Old fake wave',
    durationMs: 1000,
    steps: [{ atMs: 0, durationMs: 800, primitive: 'arm_wave', intensity: 0.8 }],
  })
  assert.deepEqual(unsupportedMotionPrimitives(action, ['tail_sway']), ['arm_wave'])

  assert.equal(compileMotionPlan(action, 'llm_plan', 'AI 动作', ['tail_sway']), null)
  assert.ok(compileMotionPlan(action, 'llm_plan', 'AI 动作', ['arm_wave']))
})
