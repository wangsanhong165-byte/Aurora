export interface VADVector {
  valence: number
  arousal: number
  dominance: number
}

export interface VADSnapshot {
  current: VADVector
  target: VADVector
  baseline: VADVector
  holdRemaining: number
}

export const VAD_PRESETS: Readonly<Record<string, VADVector>> = {
  neutral: { valence: 0, arousal: 0, dominance: 0 },
  calm: { valence: 0.2, arousal: -0.5, dominance: 0.15 },
  happy: { valence: 0.72, arousal: 0.35, dominance: 0.28 },
  cheerful: { valence: 0.78, arousal: 0.48, dominance: 0.34 },
  smile: { valence: 0.62, arousal: 0.18, dominance: 0.2 },
  joyful: { valence: 0.86, arousal: 0.68, dominance: 0.42 },
  laughing: { valence: 0.9, arousal: 0.78, dominance: 0.38 },
  playful: { valence: 0.72, arousal: 0.62, dominance: 0.5 },
  love: { valence: 0.82, arousal: 0.28, dominance: -0.08 },
  shy: { valence: 0.34, arousal: 0.35, dominance: -0.56 },
  embarrassed: { valence: -0.05, arousal: 0.55, dominance: -0.62 },
  blushing: { valence: 0.18, arousal: 0.5, dominance: -0.58 },
  surprised: { valence: 0.05, arousal: 0.88, dominance: -0.08 },
  confused: { valence: -0.2, arousal: 0.35, dominance: -0.42 },
  dizzy: { valence: -0.3, arousal: 0.4, dominance: -0.58 },
  worried: { valence: -0.56, arousal: 0.58, dominance: -0.62 },
  sad: { valence: -0.72, arousal: -0.28, dominance: -0.56 },
  cry: { valence: -0.86, arousal: 0.2, dominance: -0.7 },
  crying: { valence: -0.86, arousal: 0.2, dominance: -0.7 },
  angry: { valence: -0.72, arousal: 0.78, dominance: 0.68 },
  pout: { valence: -0.36, arousal: 0.25, dominance: 0.12 },
  blank: { valence: -0.05, arousal: -0.72, dominance: -0.1 },
  sleepy: { valence: 0.05, arousal: -0.82, dominance: -0.22 },
}

export class VADState {
  private current: VADVector
  private target: VADVector
  private baseline: VADVector
  private holdRemaining = 0
  private readonly decay = 0.16

  constructor(baseline: Partial<VADVector> = {}) {
    this.baseline = sanitize({ valence: 0, arousal: 0, dominance: 0, ...baseline })
    this.current = { ...this.baseline }
    this.target = { ...this.baseline }
  }

  setBaseline(baseline: Partial<VADVector>): void {
    this.baseline = sanitize({ ...this.baseline, ...baseline })
  }

  setEmotion(emotion: string | undefined, intensity = 1, holdSeconds = 2.4): void {
    const preset = VAD_PRESETS[(emotion || 'neutral').toLowerCase()] ?? VAD_PRESETS.neutral
    this.setTarget(scaleFromBaseline(this.baseline, preset, intensity), holdSeconds)
  }

  setTarget(target: Partial<VADVector>, holdSeconds = 2.4): void {
    this.target = sanitize({ ...this.target, ...target })
    this.holdRemaining = Math.max(0, holdSeconds)
  }

  applyStimulus(delta: Partial<VADVector>, intensity = 1): void {
    this.target = sanitize({
      valence: this.target.valence + (delta.valence ?? 0) * intensity,
      arousal: this.target.arousal + (delta.arousal ?? 0) * intensity,
      dominance: this.target.dominance + (delta.dominance ?? 0) * intensity,
    })
  }

  update(dt: number): VADSnapshot {
    const delta = Math.max(0, Math.min(0.1, dt))
    this.holdRemaining = Math.max(0, this.holdRemaining - delta)
    if (this.holdRemaining <= 0) {
      const returnWeight = 1 - Math.exp(-delta * this.decay)
      this.target = interpolate(this.target, this.baseline, returnWeight)
    }
    const response = 1 - Math.exp(-delta * 3.2)
    this.current = interpolate(this.current, this.target, response)
    return this.getSnapshot()
  }

  getSnapshot(): VADSnapshot {
    return {
      current: { ...this.current },
      target: { ...this.target },
      baseline: { ...this.baseline },
      holdRemaining: this.holdRemaining,
    }
  }
}

function scaleFromBaseline(baseline: VADVector, target: VADVector, intensity: number): VADVector {
  return interpolate(baseline, target, clamp(intensity, 0, 1))
}
function interpolate(from: VADVector, to: VADVector, amount: number): VADVector {
  return {
    valence: from.valence + (to.valence - from.valence) * amount,
    arousal: from.arousal + (to.arousal - from.arousal) * amount,
    dominance: from.dominance + (to.dominance - from.dominance) * amount,
  }
}
function sanitize(value: VADVector): VADVector {
  return {
    valence: clamp(value.valence, -1, 1),
    arousal: clamp(value.arousal, -1, 1),
    dominance: clamp(value.dominance, -1, 1),
  }
}
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
