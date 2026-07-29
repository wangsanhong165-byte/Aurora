import type { EventPayloadMap, EventSource, EventType, RuntimeEventEnvelope } from './event-types.ts'

export type EventEnvelope<K extends EventType = EventType> = RuntimeEventEnvelope<K>

export const PROTOCOL_VERSION = '3.0' as const
export const SUPPORTED_VERSIONS = new Set<string>([PROTOCOL_VERSION])

export function createEnvelope<K extends EventType>(
  eventType: K,
  payload: EventPayloadMap[K],
  overrides: Partial<Omit<EventEnvelope<K>, 'protocolVersion' | 'eventType' | 'payload'>> & {
    sessionId: string
    turnId: string | null
  },
): EventEnvelope<K> {
  return {
    protocolVersion: PROTOCOL_VERSION,
    eventId: overrides.eventId ?? `evt_${crypto.randomUUID()}`,
    eventType,
    sessionId: overrides.sessionId,
    turnId: overrides.turnId,
    sequence: overrides.sequence ?? 1,
    timestamp: overrides.timestamp ?? Date.now() / 1000,
    source: (overrides.source ?? 'frontend') as EventSource,
    payload,
  }
}

export function validateVersion(version: unknown): asserts version is '3.0' {
  if (version !== PROTOCOL_VERSION) {
    throw new Error(`Unsupported protocolVersion: ${String(version)}`)
  }
}

export class SequenceTracker {
  private lastSequence = new Map<string, number>()

  accept(sessionId: string, sequence: number): boolean {
    const last = this.lastSequence.get(sessionId) ?? 0
    if (sequence > last) {
      this.lastSequence.set(sessionId, sequence)
      return true
    }
    return false
  }

  reset(sessionId?: string): void {
    if (sessionId) this.lastSequence.delete(sessionId)
    else this.lastSequence.clear()
  }
}
