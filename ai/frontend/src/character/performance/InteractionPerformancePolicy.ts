import type { CharacterIntent } from '../CharacterBehaviorResolver'

export type InteractionEventType = 'touch' | 'drag' | 'inactivity' | 'time' | 'presence' | 'scene'

export interface InteractionEvent {
  type: InteractionEventType
  phase?: 'start' | 'move' | 'end'
  region?: 'head' | 'body' | 'unknown'
  value?: string
  intensity?: number
}

export interface InteractionDecision {
  intent: CharacterIntent
  priority: number
  cooldownMs: number
}

const DECISIONS: Record<InteractionEventType, Omit<InteractionDecision, 'intent'> & { intent: CharacterIntent }> = {
  touch: {
    intent: {
      emotion: 'happy',
      behavior: 'agree',
      intensity: 0.42,
      attention: 'user',
      energy: 0.4,
      contextTags: ['interaction', 'touch'],
    },
    priority: 60,
    cooldownMs: 1400,
  },
  drag: { intent: { emotion: 'surprised', behavior: 'react', intensity: 0.3, attention: 'user', energy: 0.35 }, priority: 35, cooldownMs: 900 },
  inactivity: { intent: { emotion: 'neutral', behavior: 'idle', intensity: 0.22, attention: 'away', energy: 0.15 }, priority: 10, cooldownMs: 12000 },
  time: { intent: { emotion: 'happy', behavior: 'greet', intensity: 0.35, attention: 'user', energy: 0.3 }, priority: 20, cooldownMs: 60000 },
  presence: { intent: { emotion: 'happy', behavior: 'greet', intensity: 0.48, attention: 'user', energy: 0.45 }, priority: 55, cooldownMs: 10000 },
  scene: { intent: { emotion: 'neutral', behavior: 'react', intensity: 0.3, attention: 'neutral', energy: 0.3 }, priority: 25, cooldownMs: 3000 },
}

/** Converts interaction semantics into an intent; it never addresses Cubism parameters. */
export class InteractionPerformancePolicy {
  private lastAccepted = new Map<InteractionEventType, number>()

  resolve(event: InteractionEvent, now = performance.now()): InteractionDecision | null {
    const decision = DECISIONS[event.type]
    const previous = this.lastAccepted.get(event.type) ?? -Infinity
    if (now - previous < decision.cooldownMs) return null
    if (event.type === 'drag' && event.phase === 'move') return null
    this.lastAccepted.set(event.type, now)
    return {
      ...decision,
      intent: {
        ...decision.intent,
        intensity: Math.max(0, Math.min(1, event.intensity ?? decision.intent.intensity ?? 1)),
      },
    }
  }
}
