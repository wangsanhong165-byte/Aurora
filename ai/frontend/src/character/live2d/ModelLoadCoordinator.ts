export type ModelLoadResult<T> =
  | { status: 'loaded'; modelName: string; generation: number; value: T }
  | { status: 'superseded'; modelName: string; generation: number }
  | { status: 'failed'; modelName: string; generation: number; error: unknown }

export interface ModelLoadToken {
  generation: number
  signal: AbortSignal
  isCurrent(): boolean
}

export class LatestModelLoadCoordinator<T> {
  private generation = 0
  private active: { modelName: string; controller: AbortController; promise: Promise<ModelLoadResult<T>> } | null = null

  run(modelName: string, loader: (token: ModelLoadToken) => Promise<T>): Promise<ModelLoadResult<T>> {
    if (this.active?.modelName === modelName) return this.active.promise
    this.active?.controller.abort()
    const generation = ++this.generation
    const controller = new AbortController()
    const token: ModelLoadToken = {
      generation,
      signal: controller.signal,
      isCurrent: () => generation === this.generation && !controller.signal.aborted,
    }
    let promise!: Promise<ModelLoadResult<T>>
    promise = (async () => {
      try {
        const value = await loader(token)
        if (!token.isCurrent()) return { status: 'superseded', modelName, generation } as const
        return { status: 'loaded', modelName, generation, value } as const
      } catch (error) {
        if (!token.isCurrent() || controller.signal.aborted) {
          return { status: 'superseded', modelName, generation } as const
        }
        return { status: 'failed', modelName, generation, error } as const
      } finally {
        if (this.active?.promise === promise) this.active = null
      }
    })()
    this.active = { modelName, controller, promise }
    return promise
  }

  cancel(): void {
    this.active?.controller.abort()
    this.active = null
    this.generation += 1
  }

  get currentGeneration(): number { return this.generation }
}
