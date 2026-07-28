// V2 ↔ V3 protocol conversion
// Single compatibility layer — all V2→V3 field remapping lives here

import { createEnvelope, type EventEnvelope } from './envelope'

// ── V2 message type mapping ──

const V2_TO_V3_TYPE: Record<string, string> = {
  text_input: 'text_input',
  audio_input: 'audio_input',
  audio_end: 'audio_end',
  interrupt: 'interrupt',
  ping: 'ping',
  command: 'command',
  avatar_request: 'avatar_request',
  avatar_accept: 'avatar_accept',
  avatar_reject: 'avatar_reject',
  assistant_message: 'assistant_message',
  assistant_chunk: 'assistant_chunk',
  user_message: 'user_message',
  tts_start: 'tts_start',
  tts_audio: 'tts_audio',
  tts_end: 'tts_end',
  runtime_status: 'runtime_status',
  tool_confirmation: 'tool_confirmation',
  character_update: 'character_update',
  session: 'session',
  error: 'error',
  pong: 'pong',
  command_response: 'command_response',
  avatar_component: 'avatar_component',
  avatar_expression: 'avatar_expression',
  avatar_motion: 'avatar_motion',
  avatar_state: 'avatar_state',
  avatar_suggestion: 'avatar_suggestion',
}

// ── Legacy field remap ──

const V2_FIELD_REMAP: Record<string, string> = {
  tone: 'emotion',
  gesture: 'behavior',
}

const V2_REMOVED_FIELDS = new Set(['intensity'])

// ── Convert V2 flat message to V3 envelope ──

export function v2ToV3Envelope(
  raw: Record<string, unknown>,
  sessionId = '',
  turnId = '',
): EventEnvelope {
  const msgType = String(raw.type ?? '')
  const v3Type = V2_TO_V3_TYPE[msgType] ?? msgType

  const payload: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (key === 'type') continue
    if (V2_REMOVED_FIELDS.has(key)) continue
    const newKey = V2_FIELD_REMAP[key] ?? key
    payload[newKey] = value
  }

  return createEnvelope(v3Type, payload, {
    protocol_version: '2.0',
    session_id: sessionId,
    turn_id: turnId,
    source: 'runtime',
    event_id: `evt_${Math.random().toString(36).slice(2, 14)}`,
    timestamp: Date.now() / 1000,
  })
}

// ── Convert V3 envelope to V2 flat message ──

export function v3ToV2Flat(envelope: EventEnvelope): Record<string, unknown> {
  const result: Record<string, unknown> = { type: envelope.type }
  for (const [key, value] of Object.entries(envelope.payload)) {
    // Invert remap
    let v2Key = key
    for (const [oldK, newK] of Object.entries(V2_FIELD_REMAP)) {
      if (newK === key) {
        v2Key = oldK
        break
      }
    }
    result[v2Key] = value
  }
  return result
}
