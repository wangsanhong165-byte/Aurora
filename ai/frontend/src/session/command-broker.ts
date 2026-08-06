export type CommandEnvelope = {
  action: string
  params: Record<string, unknown>
  requestId: string
}

type Pending = {
  resolve: (data: Record<string, unknown>) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export class CommandBroker {
  private sequence = 0
  private pending = new Map<string, Pending>()
  private readonly send: (message: CommandEnvelope) => void
  private readonly timeoutMs: number
  private readonly importTimeoutMs: number

  constructor(
    send: (message: CommandEnvelope) => void,
    timeoutMs = 15_000,
    importTimeoutMs = 30 * 60_000,
  ) {
    this.send = send
    this.timeoutMs = timeoutMs
    this.importTimeoutMs = importTimeoutMs
  }

  request(action: string, params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const requestId = `command_${Date.now()}_${++this.sequence}`
    return new Promise((resolve, reject) => {
      const timeoutMs = action === 'create_character'
        ? this.importTimeoutMs
        : this.timeoutMs
      const timer = setTimeout(() => {
        this.pending.delete(requestId)
        reject(new Error(`command timed out: ${action}`))
      }, timeoutMs)
      this.pending.set(requestId, { resolve, reject, timer })
      this.send({ action, params, requestId })
    })
  }

  resolve(requestId: string, data: Record<string, unknown>): boolean {
    const pending = this.pending.get(requestId)
    if (!pending) return false
    clearTimeout(pending.timer)
    this.pending.delete(requestId)
    pending.resolve(data)
    return true
  }

  reject(requestId: string, error: Error): boolean {
    const pending = this.pending.get(requestId)
    if (!pending) return false
    clearTimeout(pending.timer)
    this.pending.delete(requestId)
    pending.reject(error)
    return true
  }

  dispose(error = new Error('command broker disposed')): void {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer)
      pending.reject(error)
    }
    this.pending.clear()
  }
}
