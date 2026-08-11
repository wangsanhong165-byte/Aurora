import assert from 'node:assert/strict'
import test from 'node:test'

import { AutonomousAttentionController } from './performance/AutonomousAttentionController.ts'
import { PerformanceDirector } from './performance/PerformanceDirector.ts'
import { MotionArbiter } from './MotionArbiter.ts'
import { PerformanceCoordinator } from './performance/PerformanceCoordinator.ts'
import { EmbodiedTrackingController } from './performance/EmbodiedTrackingController.ts'

test('held pointer engagement prevents autonomous attention from taking gaze', () => {
  const attention = new AutonomousAttentionController(17)
  let highestEpisode = 0

  for (let frame = 0; frame < 60 * 15; frame += 1) {
    const sample = attention.update(1 / 60, {
      enabled: true,
      activity: 'idle',
      interactionEngaged: true,
    })
    highestEpisode = Math.max(highestEpisode, sample.episode)
  }

  assert.equal(highestEpisode, 0, 'autonomous gaze must stay suspended while the pointer is held')
})

test('coordinated pointer hold keeps torso alive and releases without revealing hidden idle phase', () => {
  const coordinator = new PerformanceCoordinator()
  coordinator.configure({ seed: 17 })
  const tracking = new EmbodiedTrackingController()
  tracking.setTarget(0.72, -0.15)
  let previousHead = 0
  let maxStep = 0
  let bodyPeak = 0
  let episode = 0
  let sampleCount = 0

  const runFrame = () => {
    const pose = tracking.update(1 / 60)
    const frame = coordinator.update(1 / 60, {
      activity: 'idle', emotion: 'neutral',
      vad: { valence: 0, arousal: 0, dominance: 0 },
      audioLevel: 0, enabled: true, blockedChannels: new Set(),
      tracking: { ...pose },
      trackingEngagement: tracking.getEngagementState().weight,
      explicitAttention: { values: {}, weight: 0 },
      canControlHead: true, canControlGaze: true,
    })
    const head = frame.values['head.x'] ?? 0
    if (sampleCount > 60) maxStep = Math.max(maxStep, Math.abs(head - previousHead))
    previousHead = head
    sampleCount += 1
    bodyPeak = Math.max(bodyPeak, Math.abs(frame.values['body.x'] ?? 0))
    episode = Math.max(episode, Number(frame.attention.autonomous.episode ?? 0))
  }

  for (let frame = 0; frame < 60 * 15; frame += 1) runFrame()
  tracking.release()
  for (let frame = 0; frame < 60 * 3; frame += 1) runFrame()

  assert.equal(episode, 0)
  assert.ok(bodyPeak > 0.25, `pointer focus must retain compatible torso life, got ${bodyPeak}`)
  assert.ok(maxStep < 1.2, `pointer handoff must remain continuous, max head step ${maxStep}`)
})

test('logical semantic motion layers over ambient posture instead of owning it exclusively', () => {
  let now = 0
  const arbiter = new MotionArbiter(() => now)
  arbiter.setPresets({
    emphasis: {
      name: 'emphasis',
      duration: 1_000,
      keyframes: [
        { time: 0, parameter: 'body.y', value: 0 },
        { time: 500, parameter: 'body.y', value: 3 },
        { time: 1_000, parameter: 'body.y', value: 0 },
      ],
    },
  })
  assert.equal(arbiter.request({
    name: 'emphasis', owner: 'intent:test', source: 'ai', priority: 50,
  }), true)
  now = 500
  const contribution = arbiter.update(1 / 60)[0]

  assert.equal(arbiter.ownsChannel('body'), true)
  assert.equal(arbiter.ownsExclusiveChannel('body'), false)
  assert.equal(contribution.mode, 'add')
})

test('ordinary long speech receives duration-wide semantic body language', () => {
  let now = 0
  const director = new PerformanceDirector(() => now)
  director.stage({
    turnId: 'turn-long-speech',
    emotion: 'neutral',
    behavior: 'speak',
    intensity: 0.55,
    energy: 0.58,
  })
  director.onAudioStart('turn-long-speech', 10_000)

  const [cue] = director.update()
  assert.ok(cue?.motionPlan, 'speech must have a deterministic local body-language fallback')
  assert.ok(cue.motionPlan.durationMs >= 9_000, 'fallback must span the decoded speech duration')
  assert.ok(cue.motionPlan.steps.length >= 2, 'long speech must contain multiple semantic beats')
  assert.ok(
    cue.motionPlan.steps.some(step => ['lean_forward', 'lean_back', 'sway', 'breathe', 'shrug'].includes(step.primitive)),
    'speech choreography must recruit the torso instead of only tilting the head',
  )
  assert.ok(
    cue.motionPlan.steps.at(-1)!.atMs >= 5_000,
    'the final body-language beat must occur in the latter half of the utterance',
  )
})
