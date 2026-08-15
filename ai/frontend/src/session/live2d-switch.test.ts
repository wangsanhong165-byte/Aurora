import assert from 'node:assert/strict'
import test from 'node:test'

import { eventBus } from '../core/event-bus.ts'
import { requestLive2DModelLoad, synchronizeStartupLive2DModel } from './live2d-switch.ts'

test('startup sync informs the bridge even when the visual model is already restored', async () => {
  const requests: Array<{ input: string; model: string }> = []
  const selected = await synchronizeStartupLive2DModel(
    'shirone',
    'shirone',
    async (input, init) => {
      requests.push({
        input: String(input),
        model: JSON.parse(String(init?.body)).model,
      })
      return { ok: true, status: 200 }
    },
  )

  assert.equal(selected, 'shirone')
  assert.deepEqual(requests, [{ input: '/api/set-model', model: 'shirone' }])
})

test('startup sync switches the visual model only after the bridge accepts it', async () => {
  const switched: string[] = []
  const unsubscribe = eventBus.on('character:switch_model', ({ name }) => switched.push(name))

  await synchronizeStartupLive2DModel(
    'mao_zh-Hans',
    'shirone',
    async () => ({ ok: true, status: 200 }),
  )

  assert.deepEqual(switched, ['mao_zh-Hans'])
  unsubscribe()
})

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
