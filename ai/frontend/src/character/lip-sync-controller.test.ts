import assert from 'node:assert/strict'
import test from 'node:test'

import { LipSyncController, LIP_SYNC_PRIORITY } from './LipSyncController.ts'
import { ParameterMixer } from './ParameterMixer.ts'

test('real lip-sync envelope owns the mouth over an active expression and releases continuously', () => {
  const lipSync = new LipSyncController()
  const mixer = new ParameterMixer()
  mixer.registerOwner('lip_sync', ['ParamMouthOpenY'], LIP_SYNC_PRIORITY)
  lipSync.setSpeaking(true)
  lipSync.setVolume(0.18, 0.3)

  let peak = 0
  for (let frame = 0; frame < 20; frame += 1) {
    const sample = lipSync.update(1 / 60)
    mixer.resetFrame()
    mixer.submit({
      id: 'expression:mouth', parameterId: 'ParamMouthOpenY', source: 'expression',
      channel: 'expression', value: 0, priority: 75, createdAt: frame,
    })
    mixer.setParams('lip_sync', { ParamMouthOpenY: sample.value })
    peak = Math.max(peak, mixer.resolve().ParamMouthOpenY)
  }
  assert.ok(peak > 0.2, `expected an audible mouth response, got ${peak}`)

  lipSync.setSpeaking(false)
  const release: number[] = []
  for (let frame = 0; frame < 40; frame += 1) release.push(lipSync.update(1 / 60).value)
  assert.ok(release[0] > 0, 'audio end must not snap the mouth closed')
  assert.ok(Math.max(...release.slice(1).map((value, index) => Math.abs(value - release[index]))) < 0.25)
  assert.ok(release[14] < 0.02, 'interrupted speech must close before the next diagnostic sample')
  assert.ok(release.at(-1)! < 0.02, 'mouth must recover to closed after release')
})
