import assert from 'node:assert/strict'
import test from 'node:test'

import { EVENT_TYPES, parseRuntimeEvent } from './registry.ts'

const envelope = (
  eventType: string,
  payload: Record<string, unknown>,
  turnId: string | null = 'turn-1',
): Record<string, unknown> => ({
  protocolVersion: '3.0',
  eventId: `evt-${eventType}`,
  eventType,
  sessionId: 'session-1',
  turnId,
  sequence: 1,
  source: 'frontend',
  timestamp: 1,
  payload,
})

test('registry exposes the canonical event set without character.state', () => {
  assert.ok(EVENT_TYPES.includes('user.text'))
  assert.ok(EVENT_TYPES.includes('assistant.text.completed'))
  assert.ok(EVENT_TYPES.includes('tts.audio'))
  assert.ok(!new Set<string>(EVENT_TYPES).has('character.state'))
})

test('parses a typed turn event with canonical camelCase envelope fields', () => {
  const event = parseRuntimeEvent(envelope('user.text', { text: 'hello' }))
  assert.equal(event.eventType, 'user.text')
  assert.equal(event.turnId, 'turn-1')
  assert.deepEqual(event.payload, { text: 'hello' })
})

test('allows system events without a turnId', () => {
  const event = parseRuntimeEvent(envelope('runtime.ready', { services: [] }, null))
  assert.equal(event.turnId, null)
})

test('rejects old versions and unknown events', () => {
  assert.throws(
    () => parseRuntimeEvent({ ...envelope('session.open', { capabilities: [] }, null), protocolVersion: '2.0' }),
    /protocolVersion/,
  )
  assert.throws(() => parseRuntimeEvent(envelope('unknown.event', {}, null)), /eventType/)
})

test('rejects missing, wrongly typed, and extra payload fields', () => {
  assert.throws(() => parseRuntimeEvent(envelope('user.text', {})), /text/)
  assert.throws(() => parseRuntimeEvent(envelope('user.text', { text: 42 })), /text/)
  assert.throws(() => parseRuntimeEvent(envelope('user.text', { text: 'hello', unexpected: true })), /unexpected/)
})

test('accepts independent intensity and energy on character intent', () => {
  const event = parseRuntimeEvent(envelope('character.intent', {
    emotion: 'happy',
    behavior: 'agree',
    attention: 'user',
    intensity: 0.72,
    energy: 0.38,
  }, 'turn-intent'))

  assert.deepEqual(event.payload, {
    emotion: 'happy',
    behavior: 'agree',
    attention: 'user',
    intensity: 0.72,
    energy: 0.38,
  })
})

test('rejects a turn event without turnId', () => {
  assert.throws(() => parseRuntimeEvent(envelope('user.text', { text: 'hello' }, null)), /turnId/)
})
