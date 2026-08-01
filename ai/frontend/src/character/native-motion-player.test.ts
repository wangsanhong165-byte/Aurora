import assert from 'node:assert/strict'
import test from 'node:test'

import { NativeMotionPlayer } from './live2d/NativeMotionPlayer.ts'
import { ParameterMixer } from './ParameterMixer.ts'

test('native motion emits PartOpacity curves as frame contributions', () => {
  const player = new NativeMotionPlayer()
  player.register('pose-shift', {
    Meta: { Duration: 1 },
    FadeInTime: 0,
    FadeOutTime: 0,
    Curves: [
      {
        Target: 'PartOpacity',
        Id: 'PartArmA',
        Segments: [0, 1, 0, 1, 0],
      },
    ],
  })

  assert.equal(player.play('pose-shift'), true)
  const frame = player.update(0.5)

  assert.deepEqual(frame.contributions, [
    {
      target: 'partOpacity',
      partId: 'PartArmA',
      opacity: 0.5,
      weight: 1,
    },
  ])
})

test('part opacity arbitration blends native motion over the pose baseline', () => {
  const mixer = new ParameterMixer()
  mixer.resetFrame(0)
  mixer.submitPartOpacity({
    id: 'pose:PartArmA',
    partId: 'PartArmA',
    opacity: 1,
    priority: 10,
    weight: 1,
  })
  mixer.submitPartOpacity({
    id: 'native:PartArmA',
    partId: 'PartArmA',
    opacity: 0,
    priority: 50,
    weight: 0.25,
  })

  assert.deepEqual(mixer.resolvePartOpacities(), { PartArmA: 0.75 })

  mixer.resetFrame(16)
  mixer.submitPartOpacity({
    id: 'pose:PartArmA',
    partId: 'PartArmA',
    opacity: 1,
    priority: 10,
    weight: 1,
  })
  assert.deepEqual(mixer.resolvePartOpacities(), { PartArmA: 1 })
})

test('native motion enforces a minimum 180ms fade in', () => {
  const player = new NativeMotionPlayer()
  player.register('gesture', {
    Meta: { Duration: 1 },
    FadeInTime: 0,
    Curves: [{ Target: 'Parameter', Id: 'ParamAngleX', Segments: [0, 0, 0, 1, 10] }],
  })
  player.play('gesture')
  const contribution = player.update(0.09).contributions[0]
  assert.ok(contribution.weight > 0.4 && contribution.weight < 0.6)
})

test('looping idle does not fade out and restart at every loop boundary', () => {
  const player = new NativeMotionPlayer()
  player.register('idle', {
    Meta: { Duration: 1, Loop: true },
    Curves: [{ Target: 'Parameter', Id: 'ParamAngleX', Segments: [0, 0, 0, 1, 1] }],
  })
  player.play('idle')
  const beforeLoop = player.update(0.95).contributions[0]
  const afterLoop = player.update(0.1).contributions[0]
  assert.ok(beforeLoop.weight > 0.99)
  assert.ok(afterLoop.weight > 0.99)
})

test('a lone partial native override fades from the captured model baseline', () => {
  const mixer = new ParameterMixer()
  mixer.setBaselineProvider(() => 10)
  mixer.submit({
    id: 'native-arm',
    parameterId: 'ParamArm',
    source: 'native-motion',
    channel: 'motion',
    value: 30,
    weight: 0.25,
    priority: 50,
    createdAt: 0,
  })
  assert.equal(mixer.resolve().ParamArm, 15)
})
