import assert from 'node:assert/strict'
import test from 'node:test'

import { CalibrationController } from './CalibrationController.ts'

test('calibration overrides can be set, removed and cleared without leaking invalid values', () => {
  const calibration = new CalibrationController()
  calibration.set('head.x', 7)
  calibration.set('body.y', -2)
  calibration.set('mouth.open', Number.NaN)
  calibration.setRaw('Param47', 1)

  assert.deepEqual(calibration.values(), { 'head.x': 7, 'body.y': -2 })
  calibration.remove('head.x')
  assert.deepEqual(calibration.values(), { 'body.y': -2 })
  calibration.clear()
  assert.deepEqual(calibration.values(), {})
  assert.deepEqual(calibration.rawValues(), {})
})

test('part probes restore their captured baseline exactly once when cleared', () => {
  const controller = new CalibrationController()
  assert.equal(controller.setRawPart('Part60', 0, 1), true)
  assert.deepEqual(controller.rawPartValues(), { Part60: 0 })
  controller.clearRawParts()
  assert.deepEqual(controller.rawPartValues(), {})
  assert.deepEqual(controller.takeRawPartRestores(), { Part60: 1 })
  assert.deepEqual(controller.takeRawPartRestores(), {})
})

test('raw parameter probes restore their captured baseline exactly once when cleared', () => {
  const controller = new CalibrationController()
  assert.equal(controller.setRaw('Param52', 30, 0), true)
  assert.deepEqual(controller.rawValues(), { Param52: 30 })
  controller.clearRaw()
  assert.deepEqual(controller.rawValues(), {})
  assert.deepEqual(controller.takeRawRestores(), { Param52: 0 })
  assert.deepEqual(controller.takeRawRestores(), {})
})
