import { createSeededRandom, type RandomSource } from './SeededRandom'

export interface BodySwaySample {
  headX: number
  headY: number
  headZ: number
  bodyX: number
  bodyY: number
}

interface BodySwayRanges {
  headX: readonly [number, number]
  headY: readonly [number, number]
  headZ: readonly [number, number]
  bodyX: readonly [number, number]
  bodyY: readonly [number, number]
}

const defaultRanges: BodySwayRanges = {
  headX: [-0.8, 0.8],
  headY: [-0.5, 0.55],
  headZ: [-1.1, 1.1],
  bodyX: [-1.7, 1.7],
  bodyY: [-0.75, 0.75],
}

export class BodySwayController {
  private random: RandomSource
  private from = neutralSample()
  private current = neutralSample()
  private target = neutralSample()
  private moveStartedAt = 0
  private moveDuration = 2.2
  private holdUntil = 0

  constructor(seed = 29, private readonly ranges = defaultRanges) {
    this.random = createSeededRandom(seed)
  }

  reset(seed = 29): void {
    this.random = createSeededRandom(seed)
    this.from = neutralSample()
    this.current = neutralSample()
    this.target = neutralSample()
    this.moveStartedAt = 0
    this.moveDuration = 2.2
    this.holdUntil = 0
  }

  update(timeSeconds: number, focusLevel: number, gain = 1): BodySwaySample {
    const focus = clamp(focusLevel, 0, 1)
    const weight = clamp(gain, 0, 2)
    if (focus > 0.5) {
      this.recenter(0.06 + focus * 0.08)
      return scaleSample(this.current, (1 - focus * 0.76) * weight)
    }
    if (timeSeconds >= this.holdUntil) this.pickNextTarget(timeSeconds)

    const progress = clamp(
      (timeSeconds - this.moveStartedAt) / Math.max(0.001, this.moveDuration),
      0,
      1,
    )
    const eased = quinticSmoothstep(progress)
    for (const key of sampleKeys) {
      this.current[key] = lerp(this.from[key], this.target[key], eased)
    }
    return scaleSample(this.current, weight)
  }

  private recenter(amount: number): void {
    for (const key of sampleKeys) {
      this.current[key] = lerp(this.current[key], 0, amount)
      this.from[key] = this.current[key]
      this.target[key] = 0
    }
  }

  private pickNextTarget(timeSeconds: number): void {
    this.from = { ...this.current }
    const bodyX = this.pickValue('bodyX')
    const bodyY = this.pickValue('bodyY')
    this.target = {
      bodyX,
      bodyY,
      headX: clamp(this.pickValue('headX') - bodyX * 0.32, ...this.ranges.headX),
      headY: clamp(this.pickValue('headY') + bodyY * 0.42, ...this.ranges.headY),
      headZ: clamp(this.pickValue('headZ') - bodyX * 0.24, ...this.ranges.headZ),
    }
    this.moveStartedAt = timeSeconds
    this.moveDuration = 1.45 + this.random() * 2.35
    this.holdUntil = timeSeconds + this.moveDuration + 0.55 + this.random() * 1.85
  }

  private pickValue(key: keyof BodySwayRanges): number {
    const [min, max] = this.ranges[key]
    const centerBias = this.random() < 0.22 ? 0.38 : 1
    const center = (min + max) / 2
    const half = ((max - min) / 2) * centerBias
    return center - half + this.random() * half * 2
  }
}

const sampleKeys: Array<keyof BodySwaySample> = [
  'headX', 'headY', 'headZ', 'bodyX', 'bodyY',
]

function neutralSample(): BodySwaySample {
  return { headX: 0, headY: 0, headZ: 0, bodyX: 0, bodyY: 0 }
}

function scaleSample(sample: BodySwaySample, weight: number): BodySwaySample {
  return {
    headX: sample.headX * weight,
    headY: sample.headY * weight,
    headZ: sample.headZ * weight,
    bodyX: sample.bodyX * weight,
    bodyY: sample.bodyY * weight,
  }
}

function quinticSmoothstep(value: number): number {
  const t = clamp(value, 0, 1)
  return t * t * t * (t * (t * 6 - 15) + 10)
}

function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
