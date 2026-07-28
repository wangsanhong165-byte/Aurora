// V3 Protocol Envelope — TypeScript mirror of contracts/v3/envelope.py

export interface EventEnvelope {
  protocol_version: string
  event_id: string
  session_id: string
  turn_id: string
  sequence: number
  timestamp: number
  source: string
  type: string
  payload: Record<string, unknown>
}

export const PROTOCOL_VERSION = '3.0'
export const SUPPORTED_VERSIONS = new Set(['3.0'])
export const LEGACY_VERSIONS = new Set(['2.0'])

export function createEnvelope(
  type: string,
  payload: Record<string, unknown>,
  overrides: Partial<Omit<EventEnvelope, 'type' | 'payload'>> = {},
): EventEnvelope {
  return {
    protocol_version: PROTOCOL_VERSION,
    event_id: overrides.event_id ?? `evt_${Math.random().toString(36).slice(2, 14)}`,
    session_id: overrides.session_id ?? '',
    turn_id: overrides.turn_id ?? '',
    sequence: overrides.sequence ?? 0,
    timestamp: overrides.timestamp ?? Date.now() / 1000,
    source: overrides.source ?? 'frontend',
    type,
    payload,
  }
}

export function validateVersion(version: string): void {
  if (SUPPORTED_VERSIONS.has(version)) return
  if (LEGACY_VERSIONS.has(version)) {
    throw new Error(
      `Unsupported protocol version: ${version}. Consider upgrading the client. Supported: [${[...SUPPORTED_VERSIONS].join(', ')}]`,
    )
  }
  throw new Error(`Unknown protocol version: ${version}`)
}

export function validateEnvelope(envelope: EventEnvelope): void {
  if (!envelope.protocol_version) throw new Error('protocol_version is required')
  validateVersion(envelope.protocol_version)
  if (!envelope.event_id) throw new Error('event_id is required')
  if (!envelope.session_id) throw new Error('session_id is required')
  if (!envelope.turn_id) throw new Error('turn_id is required')
  if (!envelope.type) throw new Error('type is required')
  if ((envelope.sequence ?? 0) < 0) throw new Error('sequence must be >= 0')
}

// ── Sequence tracker for dedup ──

export class SequenceTracker {
  private lastSequence = new Map<string, number>()

  accept(source: string, sequence: number): boolean {
    const last = this.lastSequence.get(source) ?? -1
    if (sequence > last) {
      this.lastSequence.set(source, sequence)
      return true
    }
    return false
  }

  reset(source?: string): void {
    if (source) {
      this.lastSequence.delete(source)
    } else {
      this.lastSequence.clear()
    }
  }
}
