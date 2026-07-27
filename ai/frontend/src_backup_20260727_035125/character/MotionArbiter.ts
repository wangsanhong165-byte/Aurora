// Owns motion scheduling only. Presets contain logical parameters, never Cubism IDs.
import type {
  NativeMotionContribution,
  NativeMotionPlayer,
} from './live2d/NativeMotionPlayer'

export type MotionSource = 'ai' | 'system' | 'pet' | 'idle'

export interface MotionKeyframe { time: number; parameter: string; value: number }
export interface SequenceStep { time: number; type: 'attention' | 'expression' | 'motion' | 'behavior'; value: string }
export interface MotionPreset {
  name: string
  duration: number
  recoveryMs?: number
  keyframes: MotionKeyframe[]
  steps?: SequenceStep[]
}
export interface LogicalParameterContribution { logicalParameter: string; value: number; source: string; priority: number }
export type ArbiterState = 'idle' | 'playing'

export function smoothstep(value: number): number {
  const t = Math.max(0, Math.min(1, value))
  return t * t * (3 - 2 * t)
}

export function sampleMotionKeyframes(
  keyframes: MotionKeyframe[],
  elapsedMs: number,
): Record<string, number> {
  const grouped = new Map<string, MotionKeyframe[]>()
  for (const frame of keyframes) {
    const frames = grouped.get(frame.parameter) ?? []
    frames.push(frame)
    grouped.set(frame.parameter, frames)
  }
  const sampled: Record<string, number> = {}
  for (const [parameter, unsorted] of grouped) {
    const frames = [...unsorted].sort((a, b) => a.time - b.time)
    if (elapsedMs <= frames[0].time) {
      sampled[parameter] = frames[0].value
      continue
    }
    const nextIndex = frames.findIndex(frame => frame.time >= elapsedMs)
    if (nextIndex < 0) {
      sampled[parameter] = frames[frames.length - 1].value
      continue
    }
    const previous = frames[nextIndex - 1]
    const next = frames[nextIndex]
    const span = Math.max(1, next.time - previous.time)
    const progress = smoothstep((elapsedMs - previous.time) / span)
    sampled[parameter] = previous.value + (next.value - previous.value) * progress
  }
  return sampled
}

export class MotionArbiter {
  private _presets: Record<string, MotionPreset> = {}
  private _queue: string[] = []
  private _currentMotion: string | null = null
  private _motionStartTime = 0
  private _motionDuration = 0
  private _state: ArbiterState = 'idle'
  private _intensity = 1
  private _executedSteps = new Set<number>()
  private _source: MotionSource = 'ai'
  private _nativePlayer: NativeMotionPlayer | null = null
  private _motionMap: Record<string, string> = {}
  private _nativeFrame: NativeMotionContribution[] = []
  private _nativeFallbackReason = ''

  setPresets(presets: Record<string, MotionPreset> | undefined): void {
    this._presets = presets ?? {}
  }

  setNativeMotionPlayer(
    player: NativeMotionPlayer | null,
    motionMap: Record<string, string> = {},
  ): void {
    this._nativePlayer = player
    this._motionMap = motionMap
    this._nativeFrame = []
  }

  play(name: string, source: MotionSource = 'ai', intensity = 1, durationOverride?: number): boolean {
    const normalized = name.toLowerCase()
    if (normalized === 'idle') {
      this.stop()
      this._nativeFallbackReason = ''
      return true
    }
    const nativeName = this._motionMap[normalized] ?? normalized
    if (this._nativePlayer?.has(nativeName) && this._nativePlayer.play(nativeName, intensity)) {
      this._currentMotion = `native:${nativeName}`
      this._motionDuration = durationOverride ?? 0
      this._motionStartTime = performance.now()
      this._intensity = intensity
      this._source = source
      this._state = 'playing'
      this._nativeFallbackReason = ''
      return true
    }
    this._nativeFallbackReason = this._nativePlayer
      ? `native motion '${nativeName}' unavailable; using logical preset`
      : 'native motion player unavailable; using logical preset'
    const preset = this._presets[name.toLowerCase()]
    if (!preset) { console.warn('[MotionArbiter] Unknown motion:', name); return false }
    this._currentMotion = name.toLowerCase()
    this._motionDuration = durationOverride ?? preset.duration
    this._motionStartTime = performance.now()
    this._intensity = intensity
    this._source = source
    this._executedSteps.clear()
    this._state = 'playing'
    console.log('[MotionArbiter] play:', name, source)
    return true
  }

  enqueue(name: string): void { if (this._presets[name.toLowerCase()]) this._queue.push(name) }
  stop(): void {
    this._nativePlayer?.stop()
    this._nativeFrame = []
    this._currentMotion = null
    this._queue = []
    this._state = 'idle'
  }
  clearQueue(): void { this._queue = [] }
  isPlaying(): boolean { return this._state === 'playing' }
  get currentMotion(): string | null { return this._currentMotion }
  get state(): ArbiterState { return this._state }
  listMotions(): string[] { return Object.keys(this._presets) }

  update(_dt: number): LogicalParameterContribution[] {
    if (!this._currentMotion) return []
    if (this._currentMotion.startsWith('native:')) {
      const result = this._nativePlayer?.update(_dt) ?? { contributions: [], done: true }
      this._nativeFrame = result.contributions
      if (result.done) {
        const next = this._queue.shift()
        if (next) this.play(next, this._source)
        else {
          this._currentMotion = null
          this._state = 'idle'
        }
      }
      return []
    }
    const preset = this._presets[this._currentMotion]
    const elapsed = performance.now() - this._motionStartTime
    if (!preset) {
      this.stop()
      return []
    }
    const recoveryMs = Math.max(0, preset.recoveryMs ?? 180)
    if (elapsed >= this._motionDuration + recoveryMs) {
      const next = this._queue.shift()
      if (next) this.play(next)
      else this.stop()
      return []
    }
    const current = sampleMotionKeyframes(
      preset.keyframes,
      Math.min(elapsed, this._motionDuration),
    )
    const recoveryWeight = elapsed <= this._motionDuration || recoveryMs === 0
      ? 1
      : 1 - smoothstep((elapsed - this._motionDuration) / recoveryMs)
    return Object.entries(current).map(([logicalParameter, value]) => ({
      logicalParameter,
      value: value * this._intensity * recoveryWeight,
      source: `motion:${preset.name}:${this._source}`,
      priority: 50,
    }))
  }

  drainNativeContributions(): NativeMotionContribution[] {
    const result = this._nativeFrame
    this._nativeFrame = []
    return result
  }

  getDebugState() {
    const elapsed = this._currentMotion ? performance.now() - this._motionStartTime : 0
    return {
      state: this._state,
      motion: this._currentMotion,
      elapsedMs: Math.round(elapsed),
      durationMs: this._motionDuration,
      progress: this._motionDuration ? Math.min(1, elapsed / this._motionDuration) : 0,
      queue: [...this._queue],
      native: this._nativePlayer?.getDebugState() ?? null,
      nativeFallbackReason: this._nativeFallbackReason,
    }
  }

  drainDueSteps(): SequenceStep[] {
    if (!this._currentMotion) return []
    const preset = this._presets[this._currentMotion]
    const elapsed = performance.now() - this._motionStartTime
    return (preset?.steps ?? []).filter((step, index) => {
      if (step.time > elapsed || this._executedSteps.has(index)) return false
      this._executedSteps.add(index)
      return true
    })
  }
}
