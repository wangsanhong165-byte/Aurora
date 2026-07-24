import type { VADVector } from './VADState'

export class VADGestureController {
  private elapsed = 0
  private cooldown = 0
  private gestureTime = 0
  private direction = 1

  update(dt: number, vad: VADVector, frequency = 1, gain = 1): Record<string, number> {
    this.elapsed += Math.max(0, dt)
    this.cooldown = Math.max(0, this.cooldown - dt)
    if (this.gestureTime <= 0 && this.cooldown <= 0 && vad.arousal > 0.22) {
      this.gestureTime = 0.9 + Math.max(0, vad.arousal) * 0.55
      this.cooldown = Math.max(2.2, 6.2 / Math.max(0.35, frequency))
      this.direction *= -1
    }
    if (this.gestureTime <= 0) return {}
    const duration = 1.45
    const progress = 1 - this.gestureTime / duration
    this.gestureTime = Math.max(0, this.gestureTime - dt)
    const envelope = Math.sin(Math.max(0, Math.min(1, progress)) * Math.PI)
    const strength = envelope * gain * (0.65 + vad.arousal * 0.55)
    return {
      'head.y': (vad.valence >= 0 ? 2.6 : -1.7) * strength,
      'head.z': this.direction * (1.2 + Math.max(0, -vad.valence)) * strength,
      'body.y': (vad.dominance >= 0 ? 0.8 : -0.65) * strength,
    }
  }
}
