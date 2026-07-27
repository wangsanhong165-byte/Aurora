import type { VADVector } from './VADState'

export class VADMicroMotionController {
  private time = 0

  update(dt: number, vad: VADVector, gain = 1): Record<string, number> {
    this.time += Math.max(0, dt)
    const energy = (0.45 + Math.max(0, vad.arousal) * 0.85) * gain
    const guarded = 0.35 + (1 - Math.abs(vad.dominance)) * 0.25
    return {
      'head.x': Math.sin(this.time * 0.73 + 0.4) * 0.72 * energy,
      'head.y': Math.sin(this.time * 0.47 + 1.7) * 0.48 * energy + vad.valence * 0.35,
      'head.z': Math.sin(this.time * 0.39 + 2.1) * 0.62 * energy - vad.dominance * 0.3,
      'body.x': Math.sin(this.time * 0.31) * 0.85 * energy,
      'body.y': Math.sin(this.time * 0.27 + 1.1) * 0.5 * energy,
      'eye.x': Math.sin(this.time * 0.61 + 0.8) * 0.08 * guarded,
      'eye.y': vad.valence * 0.035 - Math.max(0, -vad.dominance) * 0.04,
    }
  }
}
