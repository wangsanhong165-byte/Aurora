import type { ResolvedMotionStyle } from './MotionStyle'

export interface SpeechPerformanceSample {
  headX: number
  headY: number
  headZ: number
  bodyX: number
  bodyY: number
  weight: number
  state: 'idle' | 'speaking' | 'releasing'
}

export class SpeechPerformanceController {
  private elapsed = 0
  private releaseStartedAt = 0
  private previousAudioLevel = 0
  private state: SpeechPerformanceSample['state'] = 'idle'
  private style: Pick<ResolvedMotionStyle, 'speechAccentGain'> = { speechAccentGain: 1 }

  configure(style: Pick<ResolvedMotionStyle, 'speechAccentGain'>): void {
    this.style = style
  }

  setSpeaking(speaking: boolean): void {
    if (speaking) {
      if (this.state !== 'speaking') this.elapsed = 0
      this.state = 'speaking'
    } else if (this.state === 'speaking') {
      this.state = 'releasing'
      this.releaseStartedAt = this.elapsed
    }
  }

  reset(): void {
    this.elapsed = 0
    this.releaseStartedAt = 0
    this.previousAudioLevel = 0
    this.state = 'idle'
  }

  update(dt: number, audioLevel: number): SpeechPerformanceSample {
    this.elapsed += Math.max(0, dt)
    const level = clamp(audioLevel, 0, 1)
    const onsetEnvelope = this.state === 'speaking'
      ? smoothstep(Math.min(1, this.elapsed / 0.22))
      : 0
    const releaseElapsed = this.state === 'releasing'
      ? this.elapsed - this.releaseStartedAt
      : 0
    const releaseEnvelope = this.state === 'releasing'
      ? 1 - smoothstep(Math.min(1, releaseElapsed / 0.48))
      : this.state === 'speaking' ? 1 : 0
    if (this.state === 'releasing' && releaseEnvelope <= 0.001) this.state = 'idle'

    const levelRise = Math.max(0, level - this.previousAudioLevel)
    const beat = Math.max(0, Math.sin(this.elapsed * Math.PI * 2.15))
    const accentEnvelope = clamp(levelRise * 2.8 + level * beat * 0.32, 0, 1)
      * this.style.speechAccentGain
    this.previousAudioLevel += (level - this.previousAudioLevel)
      * (1 - Math.exp(-dt * 12))

    const weight = onsetEnvelope * releaseEnvelope
    return {
      headX: Math.sin(this.elapsed * 2.25 + 0.7) * 0.72 * weight,
      headY: (Math.sin(this.elapsed * 4.1) * 0.42 + accentEnvelope * 1.25) * weight,
      headZ: Math.sin(this.elapsed * 3.2) * 0.34 * weight,
      bodyX: Math.sin(this.elapsed * 1.75) * 0.38 * weight,
      bodyY: (Math.sin(this.elapsed * 1.35) * 0.2 + accentEnvelope * 0.32) * weight,
      weight,
      state: this.state,
    }
  }
}

function smoothstep(value: number): number {
  const t = clamp(value, 0, 1)
  return t * t * (3 - 2 * t)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
