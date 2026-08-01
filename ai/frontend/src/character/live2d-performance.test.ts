import assert from 'node:assert/strict'
import test from 'node:test'

import { AudioAnalyzer } from './AudioAnalyzer.ts'
import { VADGestureController } from './performance/VADGestureController.ts'
import { VADMicroMotionController } from './performance/VADMicroMotionController.ts'
import { VoiceWaitingMotionController } from './performance/VoiceWaitingMotionController.ts'
import { resolveMotionStyle } from './performance/MotionStyle.ts'
import { ParameterMixer } from './ParameterMixer.ts'
import { ParameterController, expressionTargetForBlend } from './ExpressionParameterController.ts'
import { LatestModelLoadCoordinator } from './live2d/ModelLoadCoordinator.ts'
import { AttentionController } from './performance/AttentionController.ts'
import { shouldStartAuthoredIdle } from './AvatarCapabilityProfile.ts'

test('lip-sync noise gate stays closed and calibrated output never exceeds model maximum', () => {
  const analyzer = new AudioAnalyzer()
  analyzer.configure({
    min: 0,
    max: 0.6,
    inputGain: 5,
    noiseGate: 0.02,
    attackMs: 40,
    releaseMs: 120,
    peakBoost: 0.2,
  })

  assert.equal(analyzer.analyze(0.01, 1 / 60), 0)
  const loud = analyzer.analyze(0.4, 1 / 60, 0.7)
  assert.ok(loud > 0.1)
  assert.ok(loud <= 0.6)
})

test('lip-sync releases to a closed mouth after speech stops', () => {
  const analyzer = new AudioAnalyzer()
  analyzer.configure({
    max: 0.7,
    noiseGate: 0.015,
    attackMs: 35,
    releaseMs: 90,
  })
  analyzer.analyze(0.3, 1 / 60)
  let mouth = 1
  for (let index = 0; index < 30; index += 1) {
    mouth = analyzer.analyze(0, 1 / 60)
  }
  assert.ok(mouth < 0.02)
})

test('micro motion respects unavailable body channels', () => {
  const controller = new VADMicroMotionController(17)
  const sample = controller.update(
    1 / 60,
    { valence: 0.2, arousal: 0.4, dominance: 0.1 },
    1,
    { headControl: true, bodyControl: false, gazeControl: true },
  )
  assert.equal('body.x' in sample, false)
  assert.equal('body.y' in sample, false)
  assert.equal('head.x' in sample, true)
})

test('gesture controller avoids immediate gesture-family repetition', () => {
  const controller = new VADGestureController(3)
  const vad = { valence: 0.6, arousal: 0.9, dominance: 0.4 }
  const seen: string[] = []

  for (let index = 0; index < 1200 && seen.length < 3; index += 1) {
    controller.update(1 / 30, vad, 8, 1)
    const active = controller.getState().activeGesture
    if (active && seen.at(-1) !== active) seen.push(active)
  }

  assert.ok(seen.length >= 2)
  for (let index = 1; index < seen.length; index += 1) {
    assert.notEqual(seen[index], seen[index - 1])
  }
})

test('waiting motion releases smoothly instead of snapping to zero', () => {
  const controller = new VoiceWaitingMotionController(9)
  const thinking = controller.update(0.2, 'thinking', 1)
  const releasing = controller.update(0.05, 'idle', 1)

  assert.ok(Math.abs(thinking['head.z'] ?? 0) > 0.01)
  assert.ok(Math.abs(releasing['head.z'] ?? 0) > 0.001)
  for (let index = 0; index < 30; index += 1) controller.update(0.05, 'idle', 1)
  assert.deepEqual(controller.update(0.05, 'idle', 1), {})
})

test('unknown profile motion-style presets fall back to natural instead of crashing', () => {
  const style = resolveMotionStyle({ preset: 'friendly' as any })
  assert.equal(style.preset, 'natural')
  assert.equal(style.spontaneity, 1)
})

test('expression blend semantics use the real Cubism baseline', () => {
  assert.equal(expressionTargetForBlend(0.4, 0.5, 'add', 0.2), 0.4)
  assert.ok(Math.abs(expressionTargetForBlend(0.5, 0.5, 'multiply', 0.8) - 0.6) < 1e-9)
  assert.equal(expressionTargetForBlend(1, 0.25, 'overwrite', 0.2), 0.4)
})

test('expression release keeps submitting until the real baseline is restored', () => {
  const presets: Record<string, { params: Array<{ id: string; value: number; blend?: 'overwrite' }> }> = {
    test_shy: { params: [
      { id: 'ParamCheek', value: 0.8, blend: 'overwrite' },
      { id: 'ParamPoseHand', value: 1, blend: 'overwrite' },
    ] },
    test_neutral: { params: [] },
  }
  const mixer = new ParameterMixer()
  const adapter = {
    configureMixerBaseline(target: ParameterMixer) {
      target.setBaselineProvider((id: string) => id === 'ParamCheek' ? 0.15 : 0)
    },
  } as any
  const controller = new ParameterController(name => presets[name])
  controller.attach(adapter, mixer)

  controller.applyExpression('test_shy', 1, 100, 0)
  controller.update(100)
  controller.applyExpression('test_neutral', 1, 100, 100)
  const releasing = controller.update(150)
  const finalFrame = controller.update(200)
  const afterRelease = controller.update(201)

  assert.ok(releasing.some(item => item.parameterId === 'ParamCheek' && item.value > 0.15))
  assert.ok(Math.abs((finalFrame.find(item => item.parameterId === 'ParamCheek')?.value ?? 0) - 0.15) < 1e-9)
  assert.equal(finalFrame.find(item => item.parameterId === 'ParamPoseHand')?.value, 0)
  assert.equal(afterRelease.some(item => item.parameterId === 'ParamCheek'), false)
})

test('partial override fades from lower layer while full override is exclusive', () => {
  const mixer = new ParameterMixer()
  const submit = (id: string, value: number, priority: number, weight: number) => mixer.submit({
    id,
    parameterId: 'ParamArm',
    source: id,
    channel: 'motion',
    value,
    priority,
    weight,
    createdAt: 0,
  })
  submit('idle', 10, 10, 1)
  submit('gesture', 30, 50, 0.25)
  assert.equal(mixer.resolve().ParamArm, 15)

  mixer.resetFrame()
  submit('idle', 10, 10, 1)
  submit('gesture', 30, 50, 1)
  assert.equal(mixer.resolve().ParamArm, 30)
})

test('latest model load coordinator coalesces duplicates and supersedes older generations', async () => {
  const coordinator = new LatestModelLoadCoordinator<string>()
  let resolveA!: (value: string) => void
  let resolveB!: (value: string) => void
  const a = coordinator.run('A', () => new Promise(resolve => { resolveA = resolve }))
  const duplicateA = coordinator.run('A', () => Promise.resolve('unexpected'))
  const b = coordinator.run('B', () => new Promise(resolve => { resolveB = resolve }))

  assert.equal(a, duplicateA)
  resolveA('A-ready')
  resolveB('B-ready')
  assert.deepEqual(await a, { status: 'superseded', modelName: 'A', generation: 1 })
  assert.deepEqual(await b, { status: 'loaded', modelName: 'B', generation: 2, value: 'B-ready' })
})

test('attention produces bounded away gaze, centers screen gaze, and releases neutral ownership', () => {
  const attention = new AttentionController(1)
  attention.set('away')
  const away = attention.update(0.5)
  assert.ok(Math.abs(away.values['head.x'] ?? 0) <= 8)
  assert.ok(Math.abs(away.values['eye.x'] ?? 0) <= 0.45)
  assert.ok(away.weight > 0)

  attention.set('screen')
  const screen = attention.update(0.5)
  assert.equal(screen.values['head.x'], 0)
  assert.equal(screen.values['eye.x'], 0)

  attention.set('neutral')
  for (let index = 0; index < 20; index += 1) attention.update(0.05)
  assert.deepEqual(attention.update(0.05), { values: {}, weight: 0 })
})

test('authored idle requires explicit profile opt-in', () => {
  assert.equal(shouldStartAuthoredIdle(undefined), false)
  assert.equal(shouldStartAuthoredIdle({ motions: ['speak', 'greet'] }), false)
  assert.equal(shouldStartAuthoredIdle({ motions: ['idle'] }), true)
})
