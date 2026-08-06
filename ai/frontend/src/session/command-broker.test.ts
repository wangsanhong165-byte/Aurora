import assert from 'node:assert/strict'
import test from 'node:test'

import { CommandBroker } from './command-broker.ts'

test('resolves concurrent commands with the matching request id', async () => {
  const sent: Array<Record<string, unknown>> = []
  const broker = new CommandBroker(message => sent.push(message), 100)
  const first = broker.request('get_turns', {})
  const second = broker.request('get_turns', {})

  assert.notEqual(sent[0].requestId, sent[1].requestId)
  broker.resolve(String(sent[1].requestId), { value: 2 })
  broker.resolve(String(sent[0].requestId), { value: 1 })

  assert.deepEqual(await first, { value: 1 })
  assert.deepEqual(await second, { value: 2 })
})

test('rejects all pending commands when disposed', async () => {
  const broker = new CommandBroker(() => {}, 100)
  const pending = broker.request('get_histories', {})
  broker.dispose(new Error('connection closed'))
  await assert.rejects(pending, /connection closed/)
})

test('keeps complete character imports alive beyond the normal command timeout', async () => {
  const sent: Array<Record<string, unknown>> = []
  const broker = new CommandBroker(message => sent.push(message), 5, 100)
  const pending = broker.request('create_character', {})

  await new Promise(resolve => setTimeout(resolve, 20))
  broker.resolve(String(sent[0].requestId), { character: { id: 'lantern' } })

  assert.deepEqual(await pending, { character: { id: 'lantern' } })
})
