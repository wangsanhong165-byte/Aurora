import assert from 'node:assert/strict'
import test from 'node:test'

import { EmbodiedTrackingController } from './performance/EmbodiedTrackingController.ts'

function advance(
  controller: EmbodiedTrackingController,
  seconds: number,
  dt = 1 / 120,
) {
  let sample = controller.update(dt)
  for (let elapsed = dt; elapsed < seconds; elapsed += dt) sample = controller.update(dt)
  return sample
}

test('gaze reacts quickly while small cursor corrections stay out of the torso', () => {
  const tracking = new EmbodiedTrackingController()
  tracking.setTarget(0.14, -0.1)

  const sample = advance(tracking, 0.1)

  assert.ok(sample['eye.x'] > 0.07, 'eyes should acquire a small target within 100ms')
  assert.ok(Math.abs(sample['head.x']) > 0.2, 'head should begin responding without the old long delay')
  assert.ok(Math.abs(sample['body.x']) < 0.08, 'small corrections should not puppet the whole torso')
})

test('large persistent targets recruit head then torso with distinct response times', () => {
  const tracking = new EmbodiedTrackingController()
  tracking.setTarget(0.9, 0.45)

  const early = advance(tracking, 0.14)
  const settled = advance(tracking, 0.65)

  assert.ok(early['eye.x'] > 0.55)
  assert.ok(early['head.x'] > 4.5)
  assert.ok(Math.abs(early['body.x']) < Math.abs(early['head.x']) * 0.2)
  assert.ok(Math.abs(settled['body.x']) > Math.abs(early['body.x']) + 0.35)
})

test('direction changes preserve torso inertia instead of scaling every channel together', () => {
  const tracking = new EmbodiedTrackingController()
  tracking.setTarget(0.9, 0)
  advance(tracking, 0.9)

  tracking.setTarget(-0.9, 0)
  const crossing = advance(tracking, 0.12)

  assert.ok(crossing['eye.x'] < -0.35, 'eyes should already face the new target')
  assert.ok(crossing['head.x'] < 0, 'head should follow after the eyes')
  assert.ok(crossing['body.x'] > 0, 'torso should retain old-direction momentum briefly')
})

test('recentering releases through a bounded recovery rather than snapping', () => {
  const tracking = new EmbodiedTrackingController()
  tracking.setTarget(0.8, -0.35)
  const before = advance(tracking, 0.7)

  tracking.setTarget(0, 0)
  const first = tracking.update(1 / 60)
  const recovered = advance(tracking, 1.2)

  assert.ok(Math.abs(first['body.x']) > Math.abs(before['body.x']) * 0.5)
  assert.ok(Math.abs(recovered['eye.x']) < 0.02)
  assert.ok(Math.abs(recovered['head.x']) < 0.12)
  assert.ok(Math.abs(recovered['body.x']) < 0.12)
})
