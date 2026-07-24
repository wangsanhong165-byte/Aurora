import type { VADVector } from './VADState'

export interface FACSState {
  browInnerUp: number
  browOuterUp: number
  eyeBlinkL: number
  eyeBlinkR: number
  eyeSquint: number
  mouthSmile: number
  mouthPucker: number
  gazeX: number
  gazeY: number
  headX: number
  headY: number
  headZ: number
  bodyX: number
  bodyY: number
}

export type PartialFACSState = Partial<FACSState>

export function addFACS(...layers: PartialFACSState[]): FACSState {
  const result = neutralFACS()
  for (const layer of layers) {
    for (const key of facsKeys) result[key] += layer[key] ?? 0
  }
  return clampFACS(result)
}

export function scaleFACS(state: PartialFACSState, weight: number): PartialFACSState {
  return Object.fromEntries(
    Object.entries(state).map(([key, value]) => [key, (value ?? 0) * weight]),
  ) as PartialFACSState
}

export function facsFromVAD(vad: VADVector): PartialFACSState {
  const positive = Math.max(0, vad.valence)
  const negative = Math.max(0, -vad.valence)
  const active = Math.max(0, vad.arousal)
  const calm = Math.max(0, -vad.arousal)
  const dominant = Math.max(0, vad.dominance)
  const withdrawn = Math.max(0, -vad.dominance)
  return {
    browInnerUp: negative * 0.24 + withdrawn * 0.12,
    browOuterUp: active * 0.22 + positive * 0.1,
    eyeSquint: positive * 0.16 + dominant * 0.08,
    mouthSmile: positive * 0.36,
    mouthPucker: withdrawn * 0.08,
    gazeY: withdrawn * -0.05 + dominant * 0.025,
    headY: dominant * 0.55 - withdrawn * 0.72 - negative * 0.24,
    headZ: withdrawn * 0.42,
    bodyY: dominant * 0.5 - withdrawn * 0.72 - calm * 0.2,
    bodyX: active * 0.18,
  }
}

export function neutralFACS(): FACSState {
  return {
    browInnerUp: 0, browOuterUp: 0,
    eyeBlinkL: 0, eyeBlinkR: 0, eyeSquint: 0,
    mouthSmile: 0, mouthPucker: 0,
    gazeX: 0, gazeY: 0,
    headX: 0, headY: 0, headZ: 0,
    bodyX: 0, bodyY: 0,
  }
}

function clampFACS(state: FACSState): FACSState {
  const result = { ...state }
  for (const key of facsKeys) result[key] = clamp(result[key], -1, 1)
  return result
}
const facsKeys: Array<keyof FACSState> = [
  'browInnerUp', 'browOuterUp', 'eyeBlinkL', 'eyeBlinkR', 'eyeSquint',
  'mouthSmile', 'mouthPucker', 'gazeX', 'gazeY',
  'headX', 'headY', 'headZ', 'bodyX', 'bodyY',
]
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
