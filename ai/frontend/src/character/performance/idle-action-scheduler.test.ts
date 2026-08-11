import test from 'node:test'
import assert from 'node:assert/strict'

import { IdleActionScheduler } from './IdleActionScheduler.ts'

const NEUTRAL_VAD = { valence: 0, arousal: 0, dominance: 0 }

function runSeed(seed: number, seconds = 90): { actions: Set<string> } {
  const scheduler = new IdleActionScheduler(seed, 1, 1, 3)
  const actions = new Set<string>()
  for (let t = 0; t < seconds; t += 0.1) {
    scheduler.update(t, { allowed: true, focusLevel: 0, vad: NEUTRAL_VAD })
    const state = scheduler.getState()
    if (state.activeAction) actions.add(state.activeAction)
  }
  return { actions }
}

test('idle action scheduler leaves gaze shifts to the attention owner', () => {
  const result = runSeed(17)
  assert.equal(result.actions.has('curious-look'), false)
  assert.equal(result.actions.has('side-look'), false)
  assert.ok(result.actions.size >= 4)
})

test('idle behaviours fire more often than 8s base cadence', () => {
  const scheduler = new IdleActionScheduler(11, 1, 1, 3)
  const starts: number[] = []
  let previous: string | null = null
  for (let t = 0; t < 60; t += 0.1) {
    scheduler.update(t, { allowed: true, focusLevel: 0, vad: NEUTRAL_VAD })
    const state = scheduler.getState()
    if (state.activeAction && state.activeAction !== previous) starts.push(t)
    previous = state.activeAction
  }
  // Roughly 4.5-9s cadence + duration -> expect several behaviours in 60s.
  assert.ok(starts.length >= 4, `expected >=4 distinct idle starts in 60s, got ${starts.length}`)
})
