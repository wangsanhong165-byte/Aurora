import type { AvatarPerformanceCapabilities } from '../AvatarCapabilityProfile'
import { createSeededRandom } from './SeededRandom.ts'
import type { VADVector } from './VADState'

/** Continuous low-amplitude motion built from incommensurate frequencies. */
export class VADMicroMotionController {
  private time = 0
  private readonly phase: number[]

  constructor(seed = 1) {
    const random = createSeededRandom(seed)
    this.phase = Array.from({ length: 7 }, () => random() * Math.PI * 2)
  }

  update(
    dt: number,
    vad: VADVector,
    gain = 1,
    capabilities?: AvatarPerformanceCapabilities,
  ): Record<string, number> {
    this.time += Math.max(0, dt)
    const energy = clamp(0.42 + Math.max(-0.25, vad.arousal) * 0.7, 0.18, 1.1) * gain
    const guarded = 0.3 + (1 - Math.abs(vad.dominance)) * 0.25
    const result: Record<string, number> = {}
    if (capabilities?.headControl !== false) {
      result['head.x'] = wave(this.time, .71, this.phase[0]) * .72 * energy
      result['head.y'] = wave(this.time, .43, this.phase[1]) * .46 * energy + vad.valence * .34
      result['head.z'] = wave(this.time, .37, this.phase[2]) * .58 * energy - vad.dominance * .28
    }
    if (capabilities?.bodyControl !== false) {
      result['body.x'] = wave(this.time, .29, this.phase[3]) * .82 * energy
      result['body.y'] = wave(this.time, .23, this.phase[4]) * .48 * energy
    }
    if (capabilities?.gazeControl !== false) {
      result['eye.x'] = wave(this.time, .59, this.phase[5]) * .075 * guarded
      result['eye.y'] = vad.valence * .035
        - Math.max(0, -vad.dominance) * .04
        + wave(this.time, .19, this.phase[6]) * .012
    }
    return result
  }
}

function wave(time: number, frequency: number, phase: number): number {
  return Math.sin(time * frequency + phase)
}
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
