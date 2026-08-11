import assert from 'node:assert/strict'
import test from 'node:test'

import { ParameterMixer, type ParameterContribution } from './ParameterMixer.ts'

const BASELINE = 10

function createMixer() {
  const mixer = new ParameterMixer()
  mixer.setBaselineProvider(() => BASELINE)
  return mixer
}

let seq = 0
function submit(mixer: ParameterMixer, partial: Partial<ParameterContribution> & { parameterId: string; value: number; priority: number }) {
  mixer.submit({
    id: `t${seq++}`,
    parameterId: partial.parameterId,
    source: partial.source ?? 'test',
    channel: partial.channel ?? 'motion',
    value: partial.value,
    mode: partial.mode ?? 'override',
    weight: partial.weight ?? 1,
    priority: partial.priority,
    createdAt: 0,
  })
}

function resolveOne(mixer: ParameterMixer, paramId: string): number {
  mixer.resolve()
  return mixer.getResolved(paramId)!
}

test('single full-weight override resolves to its value from the baseline', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: 30, priority: 50 })
  assert.equal(resolveOne(mixer, 'ParamArm'), 30)
})

test('single partial-weight override resolves to baseline + (value - baseline) * weight', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: 30, priority: 50, weight: 0.5 })
  assert.equal(resolveOne(mixer, 'ParamArm'), 10 + 20 * 0.5)
})

test('two opposing overrides: the highest-priority full-weight one wins outright', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: -20, priority: 10 })
  submit(mixer, { parameterId: 'ParamArm', value: 30, priority: 50 })
  // The high-priority override fully owns the parameter: no in-between blend.
  assert.equal(resolveOne(mixer, 'ParamArm'), 30)
})

test('two opposing overrides with a partial-weight winner do not blend with the loser', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: -20, priority: 10 })
  submit(mixer, { parameterId: 'ParamArm', value: 30, priority: 50, weight: 0.5 })
  // Ghost-arm regression: the winner fades from the baseline, not from the
  // loser's opposing pose. Old behaviour would resolve to -20 + (30+20)*0.5 = 5.
  assert.equal(resolveOne(mixer, 'ParamArm'), 10 + 20 * 0.5)
})

test('lower-priority override wins when it is the only override', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: -20, priority: 10 })
  assert.equal(resolveOne(mixer, 'ParamArm'), -20)
})

test('add-mode contributions accumulate on the baseline', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamMouth', value: 3, priority: 60, mode: 'add' })
  submit(mixer, { parameterId: 'ParamMouth', value: 5, priority: 60, mode: 'add' })
  assert.equal(resolveOne(mixer, 'ParamMouth'), 10 + 3 + 5)
})

test('multiply-mode contribution scales the result', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamMouth', value: 1.5, priority: 60, mode: 'multiply' })
  assert.equal(resolveOne(mixer, 'ParamMouth'), 10 * (1 + 0.5))
})

test('override winner is the base and add-mode accumulates on top', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamMouth', value: 30, priority: 50 })
  submit(mixer, { parameterId: 'ParamMouth', value: 5, priority: 60, mode: 'add' })
  assert.equal(resolveOne(mixer, 'ParamMouth'), 30 + 5)
})

test('blink multiplies the active expression so closure stays continuous', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamEyeLOpen', value: 0.2, priority: 40, source: 'blink', mode: 'multiply' })
  submit(mixer, { parameterId: 'ParamEyeLOpen', value: 0.8, priority: 75 })
  assert.ok(Math.abs(resolveOne(mixer, 'ParamEyeLOpen') - 0.16) < 1e-9)
})

test('zero-weight override resolves to the baseline', () => {
  const mixer = createMixer()
  submit(mixer, { parameterId: 'ParamArm', value: 30, priority: 50, weight: 0 })
  assert.equal(resolveOne(mixer, 'ParamArm'), BASELINE)
})

test('lip-sync (76) beats the expression layer (75) so audio can open the mouth', () => {
  const mixer = createMixer()
  // The expression layer pins ParamMouthOpenY (e.g. neutral preset writes 0).
  submit(mixer, { parameterId: 'ParamMouthOpenY', value: 0, priority: 75, source: 'expression' })
  // Lip-sync writes the audio-driven opening at a higher priority.
  submit(mixer, { parameterId: 'ParamMouthOpenY', value: 0.8, priority: 76, source: 'lip_sync' })
  assert.ok(Math.abs(resolveOne(mixer, 'ParamMouthOpenY') - 0.8) < 1e-9)
})
