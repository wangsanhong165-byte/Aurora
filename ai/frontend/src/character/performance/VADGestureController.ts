import { createSeededRandom, type RandomSource } from './SeededRandom.ts'
import type { VADVector } from './VADState'

export type VADGesture =
  | 'affirm-nod'
  | 'curious-tilt'
  | 'bright-rise'
  | 'guarded-withdraw'
  | 'confident-lean'
  | 'soft-settle'

export interface VADGestureState {
  activeGesture: VADGesture | null
  progress: number
  recentGestures: VADGesture[]
}

export class VADGestureController {
  private random: RandomSource
  private cooldown = 0
  private remaining = 0
  private duration = 1
  private direction: -1 | 1 = 1
  private active: VADGesture | null = null
  private recent: VADGesture[] = []

  constructor(seed = 1) {
    this.random = createSeededRandom(seed)
  }

  update(dt: number, vad: VADVector, frequency = 1, gain = 1): Record<string, number> {
    const delta = Math.max(0, dt)
    this.cooldown = Math.max(0, this.cooldown - delta)
    this.remaining = Math.max(0, this.remaining - delta)
    if (this.active && this.remaining <= 0) this.active = null
    if (!this.active && this.cooldown <= 0 && vad.arousal > .18) this.startGesture(vad, frequency)
    if (!this.active) return {}

    const progress = clamp(1 - this.remaining / this.duration, 0, 1)
    const envelope = Math.sin(progress * Math.PI)
    const strength = envelope * gain * clamp(.62 + vad.arousal * .48, .35, 1.2)
    return gesturePose(this.active, this.direction, strength)
  }

  getState(): VADGestureState {
    return {
      activeGesture: this.active,
      progress: this.active ? clamp(1 - this.remaining / this.duration, 0, 1) : 0,
      recentGestures: [...this.recent],
    }
  }

  private startGesture(vad: VADVector, frequency: number): void {
    const pool = gesturePool(vad)
    const fresh = pool.filter(gesture => !this.recent.includes(gesture))
    const candidates = fresh.length ? fresh : pool.filter(gesture => gesture !== this.recent.at(-1))
    const selected = (candidates.length ? candidates : pool)[
      Math.floor(this.random() * (candidates.length || pool.length))
    ]
    this.active = selected
    this.direction = this.direction === 1 ? -1 : 1
    this.duration = .78 + this.random() * .7
    this.remaining = this.duration
    this.cooldown = Math.max(8, (8 + this.random() * 5) / Math.min(1.2, Math.max(.35, frequency)))
    this.recent.push(selected)
    while (this.recent.length > 2) this.recent.shift()
  }
}

function gesturePool(vad: VADVector): VADGesture[] {
  if (vad.valence > .25 && vad.dominance > .2) return ['affirm-nod', 'bright-rise', 'confident-lean']
  if (vad.valence > .2) return ['affirm-nod', 'curious-tilt', 'bright-rise']
  if (vad.dominance < -.25) return ['guarded-withdraw', 'curious-tilt', 'soft-settle']
  if (vad.valence < -.25) return ['guarded-withdraw', 'soft-settle', 'affirm-nod']
  return ['affirm-nod', 'curious-tilt', 'soft-settle']
}

function gesturePose(
  gesture: VADGesture,
  direction: -1 | 1,
  strength: number,
): Record<string, number> {
  if (gesture === 'affirm-nod') return {
    'head.y': 3.1 * strength,
    'body.y': .55 * strength,
  }
  if (gesture === 'curious-tilt') return {
    'head.x': direction * 1.1 * strength,
    'head.z': direction * 3.2 * strength,
    'eye.x': -direction * .08 * strength,
  }
  if (gesture === 'bright-rise') return {
    'head.y': 2.1 * strength,
    'body.y': 1.15 * strength,
    'body.x': direction * .65 * strength,
  }
  if (gesture === 'guarded-withdraw') return {
    'head.y': -1.4 * strength,
    'head.z': direction * 1.2 * strength,
    'body.y': -1.05 * strength,
  }
  if (gesture === 'confident-lean') return {
    'head.x': direction * .7 * strength,
    'body.x': direction * 1.7 * strength,
    'body.y': .55 * strength,
  }
  return {
    'head.y': -1.05 * strength,
    'body.y': -.7 * strength,
    'head.z': direction * .45 * strength,
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
