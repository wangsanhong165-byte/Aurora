export interface FrameCoalescer<T> {
  schedule(value: T): void
  cancel(): void
}

export function createFrameCoalescer<T>(
  commit: (value: T) => void,
  requestFrame: (callback: () => void) => number = requestAnimationFrame,
  cancelFrame: (id: number) => void = cancelAnimationFrame,
): FrameCoalescer<T> {
  let frameId: number | null = null
  let latestValue: T
  let generation = 0

  return {
    schedule(value) {
      latestValue = value
      if (frameId !== null) return
      const scheduledGeneration = generation
      frameId = requestFrame(() => {
        if (scheduledGeneration !== generation) return
        frameId = null
        commit(latestValue)
      })
    },
    cancel() {
      generation += 1
      if (frameId !== null) cancelFrame(frameId)
      frameId = null
    },
  }
}
