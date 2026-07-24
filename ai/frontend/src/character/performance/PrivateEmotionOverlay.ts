import type { AvatarPrivateEmotionMap } from '../AvatarCapabilityProfile'
import type { VADVector } from './VADState'

export class PrivateEmotionOverlay {
  update(
    emotion: string,
    emotionIntensity: number,
    vad: VADVector,
    mappings: AvatarPrivateEmotionMap = {},
  ): Record<string, number> {
    const result: Record<string, number> = {}
    for (const mapping of Object.values(mappings)) {
      const emotionMatch = !mapping.emotions?.length
        || mapping.emotions.some(item => item.toLowerCase() === emotion.toLowerCase())
      const activation = Math.max(
        emotionMatch ? Math.max(0, Math.min(1, emotionIntensity)) : 0,
        Math.max(0, vad.valence * (mapping.valence ?? 0)),
        Math.max(0, vad.arousal * (mapping.arousal ?? 0)),
        Math.max(0, vad.dominance * (mapping.dominance ?? 0)),
      )
      const active = activation >= (mapping.threshold ?? 0.35)
      const value = (mapping.neutral ?? 0) + (active ? activation * (mapping.scale ?? 1) : 0)
      result[mapping.target] = Math.max(mapping.min ?? -Infinity, Math.min(mapping.max ?? Infinity, value))
    }
    return result
  }
}
