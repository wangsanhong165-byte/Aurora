import assert from 'node:assert/strict'
import test from 'node:test'

import { eventBus } from '../core/event-bus.ts'
import { requestLive2DModelLoad } from './live2d-switch.ts'

test('model activation resolves only after the Cubism renderer confirms the model', async () => {
  const unsubscribe = eventBus.on('character:switch_model', ({ name, requestId }) => {
    assert.equal(name, 'lantern')
    assert.ok(requestId)
    eventBus.emit('character:model_load_result', {
      name,
      requestId: requestId!,
      status: 'loaded',
    })
  })
  await requestLive2DModelLoad('lantern', 100)
  unsubscribe()
})

test('model activation rejects a Cubism parse failure', async () => {
  const unsubscribe = eventBus.on('character:switch_model', ({ name, requestId }) => {
    eventBus.emit('character:model_load_result', {
      name,
      requestId: requestId!,
      status: 'failed',
      message: 'Cubism rejected the moc3',
    })
  })
  await assert.rejects(
    requestLive2DModelLoad('broken', 100),
    /Cubism rejected the moc3/,
  )
  unsubscribe()
})
