// Temporary V2 flat-frame adapter. Deleted after the V3 frontend cutover.

export interface TransitionalEnvelope {
  protocolVersion: '3.0'
  eventId: string
  eventType: string
  sessionId: string
  turnId: string | null
  sequence: number
  timestamp: number
  source: 'frontend' | 'runtime' | 'bridge'
  payload: Record<string, unknown>
}

const FIELD_REMAP: Record<string, string> = {
  tone: 'emotion',
  gesture: 'behavior',
}

export function v2ToV3Envelope(
  raw: Record<string, unknown>,
  sessionId = '',
  turnId: string | null = null,
): TransitionalEnvelope {
  const payload: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (key === 'type') continue
    payload[FIELD_REMAP[key] ?? key] = value
  }
  return {
    protocolVersion: '3.0',
    eventId: `evt_${crypto.randomUUID()}`,
    eventType: String(raw.type ?? ''),
    sessionId,
    turnId,
    sequence: 1,
    timestamp: Date.now() / 1000,
    source: 'bridge',
    payload,
  }
}
