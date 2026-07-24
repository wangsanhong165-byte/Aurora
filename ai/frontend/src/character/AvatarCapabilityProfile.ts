import type { MotionStyleOptions } from './performance/MotionStyle'

export interface CharacterPerformancePersonality {
  expressiveness: number
  softness: number
  shyness: number
  gazeStability?: number
}

export interface AvatarPerformanceCapabilities {
  headControl?: boolean
  bodyControl?: boolean
  gazeControl?: boolean
  browControl?: boolean
  eyeBlink?: boolean
}

export interface AvatarParameterBinding {
  target: string
  neutral?: number
  scale?: number
  min?: number
  max?: number
  mode?: 'set' | 'add' | 'subtract'
  smoothing?: number
}

export type PerformanceMode = 'legacy' | 'enhanced' | 'calibration'

export interface AvatarPrivateEmotionBinding {
  target: string
  emotions?: string[]
  valence?: number
  arousal?: number
  dominance?: number
  threshold?: number
  neutral?: number
  scale?: number
  min?: number
  max?: number
}

export type AvatarPrivateEmotionMap = Record<string, AvatarPrivateEmotionBinding>

export interface AvatarCapabilityProfile {
  model: string
  expressions: string[]
  motions: string[]
  sequences?: string[]
  parameters: Record<string, Record<string, string>>
  bindings: Record<string, string | AvatarParameterBinding>
  motionStyle?: MotionStyleOptions
  personality?: CharacterPerformancePersonality
  capabilities?: AvatarPerformanceCapabilities
  motionMap?: Record<string, string>
  expressionMap?: Record<string, string>
  parameterGain?: number
  bodyMotionGain?: number
  performanceMode?: PerformanceMode
  privateEmotionMap?: AvatarPrivateEmotionMap
  /** Small per-model silent opening used only while authored native idle is active. */
  idleMouthOpen?: number
}

export function supportsExpression(profile: AvatarCapabilityProfile | undefined, name: string): boolean {
  return !profile || profile.expressions.length === 0 || profile.expressions.includes(name)
}

export function supportsMotion(profile: AvatarCapabilityProfile | undefined, name: string): boolean {
  return !profile || profile.motions.length === 0 || profile.motions.includes(name)
}

export function supportsSequence(profile: AvatarCapabilityProfile | undefined, name: string): boolean {
  return Boolean(profile?.sequences?.includes(name))
}
