import type { AvatarCapabilityProfile } from './AvatarCapabilityProfile'
import { supportsExpression, supportsMotion, supportsSequence } from './AvatarCapabilityProfile'
import type { CharacterIntent, CharacterBehaviorConfig, CharacterPresentationPlan, BehaviorMapping } from './CharacterBehaviorResolver'

export interface PerformanceModifiers {
  blinkRate: number
  bodyEnergy: number
  attention: 'user' | 'away' | 'neutral'
}

export interface PerformancePlan extends CharacterPresentationPlan {
  transitionMs: number
  holdMs: number
  modifiers: PerformanceModifiers
  motionProbability: number
}

export class CharacterPerformancePolicy {
  evaluate(intent: CharacterIntent, base: CharacterPresentationPlan, config: CharacterBehaviorConfig, profile?: AvatarCapabilityProfile): PerformancePlan {
    const intensity = Math.max(0, Math.min(1, intent.intensity ?? 1))
    const emotion = (intent.emotion || 'neutral').toLowerCase()
    const behavior = (intent.behavior || '').toLowerCase()
    const defaults: Record<string, BehaviorMapping> = {
      speak: { motion: 'nod' },
      greet: { expression: 'happy', motion: 'wave' },
      agree: { motion: 'nod' },
      disagree: { motion: 'tilt' },
      think: { motion: 'thinking', suppressIdle: true },
      excited: { expression: 'happy', motion: 'wave', motionIntensityScale: 1.15 },
    }
    const mapping = config.behaviorMap?.[behavior] ?? defaults[behavior as keyof typeof defaults] ?? {}
    const personality = config.personality ?? {}
    const requestedExpression = mapping.expression ?? base.expression ?? emotion
    const expression = supportsExpression(profile, requestedExpression) ? requestedExpression : 'neutral'
    const requestedMotion = behavior === 'greet' && supportsSequence(profile, 'greet') ? 'greet' : mapping.motion ?? base.motion
    const motion = requestedMotion && supportsMotion(profile, requestedMotion) ? requestedMotion : undefined
    const energy = Math.max(0.15, intensity * (personality.motionIntensityScale ?? 1) * (mapping.motionIntensityScale ?? 1))
    return {
      expression,
      expressionIntensity: Math.min(1, intensity * (personality.expressionIntensityScale ?? 1) * (mapping.expressionIntensityScale ?? 1)),
      motion,
      motionIntensity: energy,
      suppressIdle: base.suppressIdle || mapping.suppressIdle === true || intent.activity === 'speaking',
      transitionMs: emotion === 'surprised' ? 140 : 360,
      holdMs: intent.activity === 'speaking' ? 0 : 3000,
      modifiers: {
        blinkRate: emotion === 'surprised' ? 0.75 : emotion === 'happy' ? 1.2 : 1,
        bodyEnergy: energy,
        attention: behavior === 'think' ? 'away' : 'user',
      },
      motionProbability: motion ? ((behavior === 'greet' || behavior === 'speak') ? 1 : Math.min(0.75, 0.2 + intensity * 0.5)) : 0,
    }
  }
}
