import { normalizeSeed } from './SeededRandom.ts'

export type MotionStylePresetName = 'natural' | 'lively' | 'calm' | 'shy'

export interface MotionStyleOptions {
  preset?: MotionStylePresetName
  seed?: number
  spontaneity?: number
  gestureFrequency?: number
  gazeStability?: number
  blinkRate?: number
  breathRate?: number
  breathVariance?: number
  microMotionGain?: number
  idleActionGain?: number
  bodyMotionGain?: number
  avoidRepeatWindow?: number
  speechAccentGain?: number
}

export interface ResolvedMotionStyle {
  preset: MotionStylePresetName
  seed: number
  spontaneity: number
  gestureFrequency: number
  gazeStability: number
  blinkRate: number
  breathRate: number
  breathVariance: number
  microMotionGain: number
  idleActionGain: number
  bodyMotionGain: number
  avoidRepeatWindow: number
  speechAccentGain: number
}

const motionStylePresets: Readonly<Record<MotionStylePresetName, Readonly<MotionStyleOptions>>> = {
  natural: {
    spontaneity: 1, gestureFrequency: 1, gazeStability: 0.72,
    blinkRate: 1, breathRate: 1, breathVariance: 0.42,
    microMotionGain: 1, idleActionGain: 1, bodyMotionGain: 1,
    avoidRepeatWindow: 3, speechAccentGain: 1,
  },
  lively: {
    spontaneity: 1.32, gestureFrequency: 1.3, gazeStability: 0.5,
    blinkRate: 1.12, breathRate: 1.06, breathVariance: 0.58,
    microMotionGain: 1.16, idleActionGain: 1.12, bodyMotionGain: 1.15,
    avoidRepeatWindow: 4, speechAccentGain: 1.12,
  },
  calm: {
    spontaneity: 0.68, gestureFrequency: 0.76, gazeStability: 0.86,
    blinkRate: 0.84, breathRate: 0.82, breathVariance: 0.28,
    microMotionGain: 0.72, idleActionGain: 0.8, bodyMotionGain: 0.76,
    avoidRepeatWindow: 4, speechAccentGain: 0.72,
  },
  shy: {
    spontaneity: 0.92, gestureFrequency: 0.9, gazeStability: 0.56,
    blinkRate: 1.16, breathRate: 0.96, breathVariance: 0.52,
    microMotionGain: 0.9, idleActionGain: 0.88, bodyMotionGain: 0.82,
    avoidRepeatWindow: 4, speechAccentGain: 0.86,
  },
}

export function resolveMotionStyle(
  options: MotionStyleOptions = {},
  fallbackSeed = createMotionSeed(),
): ResolvedMotionStyle {
  const requestedPreset = options.preset
  const preset = requestedPreset && requestedPreset in motionStylePresets
    ? requestedPreset
    : 'natural'
  const base = motionStylePresets[preset]
  return {
    preset,
    seed: normalizeSeed(options.seed ?? fallbackSeed),
    spontaneity: clamp(options.spontaneity ?? base.spontaneity ?? 1, 0, 2),
    gestureFrequency: clamp(options.gestureFrequency ?? base.gestureFrequency ?? 1, 0, 2.5),
    gazeStability: clamp(options.gazeStability ?? base.gazeStability ?? 0.72, 0, 1),
    blinkRate: clamp(options.blinkRate ?? base.blinkRate ?? 1, 0.25, 2.5),
    breathRate: clamp(options.breathRate ?? base.breathRate ?? 1, 0.5, 1.8),
    breathVariance: clamp(options.breathVariance ?? base.breathVariance ?? 0.42, 0, 1),
    microMotionGain: clamp(options.microMotionGain ?? base.microMotionGain ?? 1, 0, 2),
    idleActionGain: clamp(options.idleActionGain ?? base.idleActionGain ?? 1, 0, 2),
    bodyMotionGain: clamp(options.bodyMotionGain ?? base.bodyMotionGain ?? 1, 0, 2),
    avoidRepeatWindow: Math.round(clamp(
      options.avoidRepeatWindow ?? base.avoidRepeatWindow ?? 3, 0, 8,
    )),
    speechAccentGain: clamp(options.speechAccentGain ?? base.speechAccentGain ?? 1, 0, 2),
  }
}

export function deriveMotionSeed(seed: number, channel: number): number {
  let value = (normalizeSeed(seed) ^ Math.imul(channel + 1, 0x9e3779b1)) >>> 0
  value ^= value >>> 16
  value = Math.imul(value, 0x85ebca6b) >>> 0
  value ^= value >>> 13
  value = Math.imul(value, 0xc2b2ae35) >>> 0
  value ^= value >>> 16
  return normalizeSeed(value)
}

function createMotionSeed(): number {
  const time = Date.now() >>> 0
  const random = Math.floor(Math.random() * 0xffffffff) >>> 0
  return normalizeSeed(time ^ random)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
