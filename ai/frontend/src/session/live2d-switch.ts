import { eventBus } from '../core/event-bus.ts'

let requestSequence = 0

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
