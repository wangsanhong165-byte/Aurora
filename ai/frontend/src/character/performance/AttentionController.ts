export type AttentionTarget = 'user' | 'screen' | 'away' | 'neutral'

export class AttentionController {
  private target: AttentionTarget = 'neutral'
  private weight = 0
  private awaySign: 1 | -1
  private remainingSeconds = Infinity

  constructor(seed = 1) {
    this.awaySign = seed % 2 === 0 ? -1 : 1
  }

  set(target: AttentionTarget, durationMs?: number): void {
    if (target === 'away' && this.target !== 'away') this.awaySign = this.awaySign === 1 ? -1 : 1
    this.target = target
    this.remainingSeconds = durationMs === undefined ? Infinity : Math.max(0.3, durationMs / 1000)
  }

  reset(): void {
    this.target = 'neutral'
    this.weight = 0
    this.remainingSeconds = Infinity
  }

  update(dt: number): { values: Record<string, number>; weight: number } {
    if (Number.isFinite(this.remainingSeconds)) {
      this.remainingSeconds -= Math.max(0, dt)
      if (this.remainingSeconds <= 0) this.target = 'neutral'
    }
    const ownsAttention = this.target === 'screen' || this.target === 'away'
    const targetWeight = ownsAttention ? 1 : 0
    this.weight += (targetWeight - this.weight) * (1 - Math.exp(-Math.max(0, dt) * 8))
    if (this.weight < 0.001 && !ownsAttention) {
      this.weight = 0
      return { values: {}, weight: 0 }
    }
    if (this.target === 'away') {
      return {
        values: {
          'eye.x': this.awaySign * 0.35,
          'eye.y': 0.04,
          'head.x': this.awaySign * 6,
          'head.y': 0.5,
        },
        weight: this.weight,
      }
    }
    return {
      values: { 'eye.x': 0, 'eye.y': 0, 'head.x': 0, 'head.y': 0 },
      weight: this.weight,
    }
  }
}
