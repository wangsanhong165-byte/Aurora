// Lightweight typed event bus for decoupled communication

type Handler<T> = (event: T) => void

export interface EventMap {
  'character:emotion': { emotion: string; intensity: number }
  'character:intent': { emotion: string; behavior: string; intensity: number }
  'character:interaction': { type: 'touch' | 'drag' | 'inactivity' | 'time' | 'presence' | 'scene'; phase?: 'start' | 'move' | 'end'; region?: 'head' | 'body' | 'unknown'; value?: string; intensity?: number }
  'character:performance_tuning': { mode?: 'legacy' | 'enhanced' | 'calibration'; parameterGain?: number; bodyMotionGain?: number }
  'character:native_catalog': { motions: string[]; expressions: string[] }
  'character:native_preview': { type: 'motion' | 'expression'; name: string }
  'character:activity': { activity: string }
  'character:performance': { emotion: string; behavior: string; expression: string; motion: string; profile: string; transitionMs: number; holdMs: number; motionProbability: number; modifiers: Record<string, unknown> }
  'character:performance_debug': {
    activity: string
    previousActivity: string
    transitionProgress: number
    vad: {
      current: { valence: number; arousal: number; dominance: number }
      target: { valence: number; arousal: number; dominance: number }
      baseline: { valence: number; arousal: number; dominance: number }
      holdRemaining: number
    }
    expression: { name: string; intensity: number }
    motion: Record<string, unknown>
    idle: Record<string, number | string | null>
    lipSync: Record<string, number | boolean>
    pose: Array<{ activeId: string; members: string[] }>
    profileCoverage: { bindingCount: number; resolvedCount: number; coverage: number; missingBindings: Array<{ logical: string; target: string }> }
    performanceTuning: { mode: 'legacy' | 'enhanced' | 'calibration'; parameterGain: number; bodyMotionGain: number }
    contestedParameters: Record<string, Array<{ source: string; value: number; priority: number }>>
  }
  'audio:play': { audio: string; format: string; volumeArray?: number[] }
  'audio:stop': void
  'audio:volume': { volume: number }
  'audio:start': void
  'audio:end': void
  'connection:change': { connected: boolean }
  'runtime:status': { status: string; message?: string }
  'runtime:error': { code: string; message: string; requestId?: string }
  'runtime:message': { text: string; reasoning?: string; segments?: Array<{ text: string; emotion: string; behavior: string }>; diagnostics?: Record<string, unknown> }
  'runtime:chunk': { text: string; delta: string }
  'runtime:tts_start': { format: string; sequence: number }
  'runtime:tts_end': { reason: string }
  'runtime:command_response': { action: string; data: Record<string, unknown>; requestId?: string }
  'runtime:session': { status: string; config: Record<string, unknown> }
  'runtime:user_message': { text: string }
  'runtime:permission_requested': {
    requestId: string
    capability: string
    args: Record<string, unknown>
    risk: string
  }
  'runtime:character_intent': { emotion: string; behavior: string; attention: string; energy: number; intensity: number; durationMs?: number; naturalVAD?: { valence: number; arousal: number; dominance: number }; contextTags?: string[] }
  'runtime:telemetry': { events: Array<Record<string, unknown>> }
  'character:runtime-telemetry': {
    type: string
    turnId?: string
    spanId?: string
    durationMs?: number
    metadata?: Record<string, unknown>
  }
  'character:switch_model': { name: string }
  'accessory:loaded': { parts: Record<string, string>; state: Record<string, boolean> }
  'accessory:toggle': { label: string }
  'accessory:set': { label: string; enabled: boolean }
  'accessory:state_changed': { label: string; enabled: boolean; parts: Record<string, string>; state: Record<string, boolean> }
  'accessory:refresh': void
  // Avatar control layer events
  'avatar:component_update': { name: string; displayName: string; enabled: boolean; controller: string; priority: number; expression: string; paramIds: string[] }
  'avatar:expression_update': { name: string; intensity: number; controller: string; priority: number }
  'avatar:motion_update': { name: string; controller: string; priority: number; loop: boolean }
  'avatar:state_restored': { components: Record<string, boolean>; expression: string; intensity: number; motion: string }
  'avatar:suggestion': { target: string; name: string; action: string; reason: string; suggestionId: string }
  'avatar:send': Record<string, unknown>
}

export type EventName = keyof EventMap

export class EventBus {
  private listeners = new Map<string, Set<Handler<any>>>()

  on<K extends EventName>(event: K, handler: Handler<EventMap[K]>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(handler)
    return () => this.listeners.get(event)?.delete(handler)
  }

  off<K extends EventName>(event: K, handler: Handler<EventMap[K]>): void {
    this.listeners.get(event)?.delete(handler)
  }

  emit<K extends EventName>(event: K, data: EventMap[K]): void {
    this.listeners.get(event)?.forEach((h) => h(data))
  }

  clear(): void {
    this.listeners.clear()
  }
}

// Singleton instance
export const eventBus = new EventBus()
