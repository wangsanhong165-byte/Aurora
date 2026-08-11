import assert from 'node:assert/strict'
import test from 'node:test'

import { SpeechPerformanceController } from './SpeechPerformanceController.ts'

test('speech posture visibly recruits head and torso without discontinuous frames', () => {
  const speech = new SpeechPerformanceController()
  speech.configure({ speechAccentGain: 1.08 })
  speech.setSpeaking(true)
  let previous = speech.update(1 / 60, 0)
  let headPeak = 0
  let bodyPeak = 0
  let maxDelta = 0
  for (let frame = 1; frame < 360; frame += 1) {
    const level = 0.16 + Math.max(0, Math.sin(frame * 0.21)) * 0.28
    const sample = speech.update(1 / 60, level)
    headPeak = Math.max(headPeak, Math.abs(sample.headX), Math.abs(sample.headY), Math.abs(sample.headZ))
    bodyPeak = Math.max(bodyPeak, Math.abs(sample.bodyX), Math.abs(sample.bodyY))
    maxDelta = Math.max(
      maxDelta,
      Math.abs(sample.headX - previous.headX),
      Math.abs(sample.headY - previous.headY),
      Math.abs(sample.bodyX - previous.bodyX),
    )
    previous = sample
  }

  assert.ok(headPeak >= 1.5, `speech head peak too subtle: ${headPeak}`)
  assert.ok(bodyPeak >= 0.65, `speech torso peak too subtle: ${bodyPeak}`)
  assert.ok(maxDelta < 0.8, `speech frame delta is too abrupt: ${maxDelta}`)
})

test('speech posture releases over time instead of snapping to neutral', () => {
  const speech = new SpeechPerformanceController()
  speech.setSpeaking(true)
  for (let frame = 0; frame < 90; frame += 1) speech.update(1 / 60, 0.35)
  speech.setSpeaking(false)
  const first = speech.update(1 / 60, 0)
  assert.ok(first.weight > 0.5)
  let final = first
  for (let frame = 0; frame < 45; frame += 1) final = speech.update(1 / 60, 0)
  assert.equal(final.state, 'idle')
  assert.ok(Math.abs(final.headX) < 0.01)
  assert.ok(Math.abs(final.bodyX) < 0.01)
})
