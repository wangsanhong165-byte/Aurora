// Translates runtime character intent into a model-agnostic presentation plan.
// It never writes Cubism parameters and deliberately knows nothing about the renderer.

export interface CharacterIntent {
  emotion?: string
  behavior?: string
  intensity?: number
  activity?: string
  attention?: 'user' | 'screen' | 'away' | 'neutral'
  energy?: number
  durationMs?: number
}

export interface BehaviorMapping {
  expression?: string
  motion?: string
  expressionIntensityScale?: number
  motionIntensityScale?: number
  suppressIdle?: boolean
}

export interface PersonalityModifier {
  expressionIntensityScale?: number
  motionIntensityScale?: number
  emotionBehavior?: Record<string, string>
}

export interface CharacterBehaviorConfig {
  emotionMap?: Record<string, string>
  behaviorMap?: Record<string, BehaviorMapping>
  personality?: PersonalityModifier
}

export interface CharacterPresentationPlan {
  expression: string
  expressionIntensity: number
  motion?: string
  motionIntensity: number
  suppressIdle: boolean
}

const DEFAULT_BEHAVIORS: Record<string, BehaviorMapping> = {
  speak: { motion: 'nod' },
  greet: { motion: 'wave', expression: 'happy' },
  agree: { motion: 'nod' },
  disagree: { motion: 'tilt' },
  think: { motion: 'thinking', suppressIdle: true },
  excited: { motion: 'wave', expression: 'happy', motionIntensityScale: 1.15 },
  listen: { expression: 'neutral' },
  idle: { expression: 'neutral' },
}

const clamp = (value: number) => Math.max(0, Math.min(1, value))

export class CharacterBehaviorResolver {
  private _config: CharacterBehaviorConfig = {}

  setConfig(config: CharacterBehaviorConfig | undefined): void {
    this._config = config ?? {}
  }

  getConfig(): CharacterBehaviorConfig { return this._config }

  resolve(intent: CharacterIntent): CharacterPresentationPlan {
    const intensity = clamp(intent.intensity ?? 1)
    const emotion = (intent.emotion || 'neutral').toLowerCase()
    const behavior = (intent.behavior || '').toLowerCase()
    const personality = this._config.personality ?? {}
    const personalityBehavior = personality.emotionBehavior?.[emotion]
    const mapping = this._config.behaviorMap?.[behavior]
      ?? DEFAULT_BEHAVIORS[behavior]
      ?? (personalityBehavior ? this._config.behaviorMap?.[personalityBehavior] ?? DEFAULT_BEHAVIORS[personalityBehavior] : undefined)
      ?? {}

    // Keep the semantic emotion as the expression input. ExpressionController
    // resolves it through the active model's emotionMap.
    const expression = mapping.expression ?? emotion
    const expressionIntensity = clamp(
      intensity * (mapping.expressionIntensityScale ?? 1) * (personality.expressionIntensityScale ?? 1),
    )
    const motion = mapping.motion
    const motionIntensity = clamp(
      intensity * (mapping.motionIntensityScale ?? 1) * (personality.motionIntensityScale ?? 1),
    )

    const plan = {
      expression,
      expressionIntensity,
      motion,
      motionIntensity,
      suppressIdle: mapping.suppressIdle === true || intent.activity === 'speaking',
    }
    console.log('[BEHAVIOR RESOLVED]', { intent, plan })
    return plan
  }
}
