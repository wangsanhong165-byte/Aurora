export interface FrameTimingSample {
  intervalMs: number
  workMs: number
  controllerMs: number
  mixMs: number
  modelMs: number
  renderMs: number
}

export interface FrameTimingSnapshot extends FrameTimingSample {
  sampleCount: number
  averageIntervalMs: number
  p95IntervalMs: number
  maxIntervalMs: number
  longFrameCount: number
}

const EMPTY_SAMPLE: FrameTimingSample = {
  intervalMs: 0,
  workMs: 0,
  controllerMs: 0,
  mixMs: 0,
  modelMs: 0,
  renderMs: 0,
}

/** Bounded recorder: every frame is observed, snapshots are emitted at 4 Hz. */
export class FrameTimingMonitor {
  private readonly samples: Array<FrameTimingSample | undefined>
  private readonly capacity: number
  private writeIndex = 0
  private sampleCount = 0

  constructor(capacity = 240) {
    this.capacity = Math.max(30, Math.round(capacity))
    this.samples = new Array(this.capacity)
  }

  record(sample: FrameTimingSample): void {
    this.samples[this.writeIndex] = {
      intervalMs: finite(sample.intervalMs),
      workMs: finite(sample.workMs),
      controllerMs: finite(sample.controllerMs),
      mixMs: finite(sample.mixMs),
      modelMs: finite(sample.modelMs),
      renderMs: finite(sample.renderMs),
    }
    this.writeIndex = (this.writeIndex + 1) % this.capacity
    this.sampleCount = Math.min(this.sampleCount + 1, this.capacity)
  }

  snapshot(): FrameTimingSnapshot {
    if (!this.sampleCount) {
      const latest = EMPTY_SAMPLE
      return { ...latest, sampleCount: 0, averageIntervalMs: 0, p95IntervalMs: 0, maxIntervalMs: 0, longFrameCount: 0 }
    }
    const latestIndex = (this.writeIndex - 1 + this.capacity) % this.capacity
    const latest = this.samples[latestIndex] ?? EMPTY_SAMPLE
    const intervals = new Array<number>(this.sampleCount)
    for (let index = 0; index < this.sampleCount; index += 1) {
      const sampleIndex = (this.writeIndex - this.sampleCount + index + this.capacity) % this.capacity
      intervals[index] = this.samples[sampleIndex]?.intervalMs ?? 0
    }
    intervals.sort((a, b) => a - b)
    const total = intervals.reduce((sum, value) => sum + value, 0)
    return {
      ...latest,
      sampleCount: intervals.length,
      averageIntervalMs: total / intervals.length,
      p95IntervalMs: intervals[Math.min(intervals.length - 1, Math.floor(intervals.length * 0.95))],
      maxIntervalMs: intervals.at(-1) ?? 0,
      longFrameCount: intervals.filter(value => value > 33.34).length,
    }
  }
}

function finite(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0
}
