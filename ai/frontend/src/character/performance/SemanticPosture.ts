import type { VADVector } from './VADState.ts'

/** Convert affect into a coherent whole-body stance, leaving lateral motion to sway/attention. */
export function semanticPostureFromVAD(vad: VADVector, gain = 1): Record<string, number> {
  const positive = Math.max(0, vad.valence)
  const negative = Math.max(0, -vad.valence)
  const active = Math.max(0, vad.arousal)
  const calm = Math.max(0, -vad.arousal)
  const dominant = Math.max(0, vad.dominance)
  const withdrawn = Math.max(0, -vad.dominance)
  const headY = (
    positive * 0.9 - negative * 1.5
    + dominant * 1.5 - withdrawn * 1.2
    + active * 0.25 - calm * 0.15
  ) * 1.8 * gain
  const bodyY = (
    positive * 0.6 - negative * 1.2
    + dominant * 1.5 - withdrawn
    + active * 0.2 - calm * 0.12
  ) * 1.5 * gain
  const tilt = (withdrawn * 0.72 - dominant * 0.22) * 1.6 * gain
  return {
    'head.y': headY,
    'head.z': tilt,
    'body.y': bodyY,
    'body.z': -tilt * 0.32,
  }
}
