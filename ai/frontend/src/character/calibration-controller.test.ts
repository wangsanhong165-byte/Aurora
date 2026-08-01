import assert from 'node:assert/strict'
import test from 'node:test'

import { CalibrationController } from './CalibrationController.ts'

test('calibration overrides can be set, removed and cleared without leaking invalid values', () => {
  const calibration = new CalibrationController()
  calibration.set('head.x', 7)
  calibration.set('body.y', -2)
  calibration.set('mouth.open', Number.NaN)

  assert.deepEqual(calibration.values(), { 'head.x': 7, 'body.y': -2 })
  calibration.remove('head.x')
  assert.deepEqual(calibration.values(), { 'body.y': -2 })
  calibration.clear()
  assert.deepEqual(calibration.values(), {})
})
