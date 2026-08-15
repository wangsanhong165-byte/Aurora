import { eventBus } from '../core/event-bus.ts'

let requestSequence = 0

type ModelSetter = (input: RequestInfo | URL, init?: RequestInit) => Promise<Pick<Response, 'ok' | 'status'>>

/** Align the Bridge capability registry with the model restored by the UI. */
export async function synchronizeStartupLive2DModel(
  persistedModel: string,
  startupModel: string,
  setModel: ModelSetter = fetch,
): Promise<string> {
  const selected = persistedModel || startupModel
  if (!selected) return ''
  const response = await setModel('/api/set-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: selected }),
  })
  if (!response.ok) {
    throw new Error(`Live2D startup model sync failed: ${response.status}`)
  }
  if (persistedModel && persistedModel !== startupModel) {
    eventBus.emit('character:switch_model', { name: persistedModel })
  }
  return selected
}

export function requestLive2DModelLoad(name: string, timeoutMs = 30_000): Promise<void> {
  const requestId = `model_load_${++requestSequence}`
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      unsubscribe()
      reject(new Error(`Live2D model load timed out: ${name}`))
    }, timeoutMs)
    const unsubscribe = eventBus.on('character:model_load_result', (result) => {
      if (result.requestId !== requestId || result.name !== name) return
      clearTimeout(timeout)
      unsubscribe()
      if (result.status === 'loaded') {
        resolve()
      } else {
        reject(new Error(result.message || `Live2D model load ${result.status}: ${name}`))
      }
    })
    eventBus.emit('character:switch_model', { name, requestId })
  })
}
