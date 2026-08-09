// Owns motion scheduling only. Presets contain logical parameters, never Cubism IDs.
import type {
  NativeMotionContribution,
  NativeMotionPlayer,
} from './live2d/NativeMotionPlayer'

export type MotionSource = 'ai' | 'system' | 'pet' | 'idle'
export type MotionChannel = 'head' | 'body' | 'gaze' | 'expression' | 'mouth' | 'tail' | 'full'

export interface MotionKeyframe { time: number; parameter: string; value: number }
export interface SequenceStep { time: number; type: 'attention' | 'expression' | 'motion' | 'behavior'; value: string }
export interface MotionPreset {
  name: string
  duration: number
  /** Logical motions enter from the model baseline instead of snapping. */
  fadeInMs?: number
  recoveryMs?: number
  keyframes: MotionKeyframe[]
  steps?: SequenceStep[]
}
export interface LogicalParameterContribution {
  logicalParameter: string
  value: number
  source: string
  priority: number
  weight?: number
}
export interface MotionRequest {
  name: string
  owner: string
  source: MotionSource
  priority: number
  channels?: MotionChannel[]
  turnId?: string
  timeoutMs?: number
  intensity?: number
  durationMs?: number
}
export type ArbiterState = 'idle' | 'playing'

interface ActiveMotion {
  request: {
    name: string
    owner: string
    source: MotionSource
    priority: number
    channels: MotionChannel[]
    turnId?: string
    timeoutMs?: number
    intensity: number
    durationMs?: number
  }
  preset?: MotionPreset
  nativeName?: string
  startedAt: number
  duration: number
  expiresAt: number
  executedSteps: Set<number>
}

export function smoothstep(value: number): number {
  const t = clamp(value, 0, 1)
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

/**
 * Arbitrates semantic/native motion ownership. Multiple logical motions may
 * coexist when their channels do not overlap. Cubism writes remain outside
 * this module and flow through ParameterMixer.
 */
export class MotionArbiter {
  private presets: Record<string, MotionPreset> = {}
  private queue: Array<{ name: string; source: MotionSource; intensity: number }> = []
  private active = new Map<string, ActiveMotion>()
  private nativePlayer: NativeMotionPlayer | null = null
  private motionMap: Record<string, string> = {}
  private nativeFrame: NativeMotionContribution[] = []
  private nativeFallbackReason = ''
  private readonly clock: () => number

  constructor(clock: () => number = () => performance.now()) {
    this.clock = clock
  }

  setPresets(presets: Record<string, MotionPreset> | undefined): void {
    this.presets = presets ?? {}
  }

  registerPreset(preset: MotionPreset): void {
    this.presets[preset.name.toLowerCase()] = preset
  }

  setNativeMotionPlayer(
    player: NativeMotionPlayer | null,
    motionMap: Record<string, string> = {},
  ): void {
    this.stop()
    this.nativePlayer = player
    this.motionMap = motionMap
  }

  request(input: MotionRequest): boolean {
    const name = input.name.toLowerCase()
    const nativeName = this.motionMap[name] ?? name
    const nativeAvailable = Boolean(this.nativePlayer?.has(nativeName))
    const preset = this.presets[name]
    if (!nativeAvailable && !preset) {
      if (name === 'idle') {
        this.stop()
        this.nativeFallbackReason = ''
        return true
      }
      this.nativeFallbackReason = this.nativePlayer
        ? `native motion '${nativeName}' unavailable; logical preset missing`
        : 'native motion player unavailable; logical preset missing'
      console.warn('[MotionArbiter] Unknown motion:', input.name)
      return false
    }

    const channels = normalizeChannels(
      input.channels?.length
        ? input.channels
        : nativeAvailable
          ? ['full']
          : inferChannels(preset!),
    )
    const request: ActiveMotion['request'] = {
      name,
      owner: input.owner,
      source: input.source,
      priority: input.priority,
      channels,
      turnId: input.turnId,
      timeoutMs: input.timeoutMs,
      durationMs: input.durationMs,
      intensity: clamp(input.intensity ?? 1, 0, 2),
    }
    const conflicts = [...this.active.values()].filter(active =>
      active.request.owner !== request.owner
      && channelsOverlap(active.request.channels, request.channels))
    if (conflicts.some(active => active.request.priority > request.priority)) return false

    this.cancelOwner(request.owner)
    for (const conflict of conflicts) this.cancelOwner(conflict.request.owner)

    if (nativeAvailable && !this.nativePlayer!.play(nativeName, request.intensity)) {
      this.nativeFallbackReason = `native motion '${nativeName}' failed to start`
      return false
    }

    const now = this.clock()
    const duration = input.durationMs ?? preset?.duration ?? 0
    this.active.set(request.owner, {
      request,
      preset: nativeAvailable ? undefined : preset,
      nativeName: nativeAvailable ? nativeName : undefined,
      startedAt: now,
      duration,
      expiresAt: input.timeoutMs === undefined
        ? Infinity
        : now + Math.max(0, input.timeoutMs),
      executedSteps: new Set(),
    })
    this.nativeFallbackReason = nativeAvailable
      ? ''
      : this.nativePlayer
        ? `native motion '${nativeName}' unavailable; using logical preset`
        : 'native motion player unavailable; using logical preset'
    return true
  }

  play(
    name: string,
    source: MotionSource = 'ai',
    intensity = 1,
    durationOverride?: number,
  ): boolean {
    return this.request({
      name,
      owner: `legacy:${source}`,
      source,
      priority: sourcePriority(source),
      intensity,
      durationMs: durationOverride,
    })
  }

  enqueue(name: string, source: MotionSource = 'ai', intensity = 1): void {
    const normalized = name.toLowerCase()
    const nativeName = this.motionMap[normalized] ?? normalized
    if (this.presets[normalized] || this.nativePlayer?.has(nativeName)) {
      this.queue.push({ name, source, intensity })
    }
  }

  stop(): void {
    this.nativePlayer?.stop()
    this.nativeFrame = []
    this.active.clear()
    this.queue = []
  }

  cancelOwner(owner: string): boolean {
    const active = this.active.get(owner)
    if (!active) return false
    if (active.nativeName) {
      this.nativePlayer?.stop()
      this.nativeFrame = []
    }
    this.active.delete(owner)
    return true
  }

  cancelTurn(turnId: string): number {
    const owners = [...this.active.values()]
      .filter(active => active.request.turnId === turnId)
      .map(active => active.request.owner)
    owners.forEach(owner => this.cancelOwner(owner))
    return owners.length
  }

  clearQueue(): void { this.queue = [] }
  isPlaying(): boolean { return this.active.size > 0 }
  ownsChannel(channel: MotionChannel): boolean {
    return [...this.active.values()].some(active =>
      active.request.channels.includes('full') || active.request.channels.includes(channel))
  }
  getActiveChannels(): MotionChannel[] {
    const channels = new Set<MotionChannel>()
    for (const active of this.active.values()) {
      for (const channel of active.request.channels) channels.add(channel)
    }
    return [...channels]
  }
  get currentMotion(): string | null {
    const active = this.primaryActive()
    if (!active) return null
    return active.nativeName ? `native:${active.nativeName}` : active.request.name
  }
  get state(): ArbiterState { return this.isPlaying() ? 'playing' : 'idle' }
  listMotions(): string[] { return Object.keys(this.presets) }

  update(dt: number): LogicalParameterContribution[] {
    const now = this.clock()
    const contributions: LogicalParameterContribution[] = []
    for (const active of [...this.active.values()]) {
      if (now >= active.expiresAt) {
        this.cancelOwner(active.request.owner)
        continue
      }
      if (active.nativeName) {
        const result = this.nativePlayer?.update(dt) ?? { contributions: [], done: true }
        this.nativeFrame = result.contributions
        if (result.done) this.cancelOwner(active.request.owner)
        continue
      }
      const preset = active.preset
      if (!preset) {
        this.cancelOwner(active.request.owner)
        continue
      }
      const elapsed = now - active.startedAt
        const recoveryMs = Math.max(300, Math.min(600, preset.recoveryMs ?? 420))
      if (elapsed >= active.duration + recoveryMs) {
        this.cancelOwner(active.request.owner)
        continue
      }
      const current = sampleMotionKeyframes(
        preset.keyframes,
        Math.min(elapsed, active.duration),
      )
      const fadeInMs = Math.max(0, Math.min(500, preset.fadeInMs ?? 180))
      const fadeInWeight = fadeInMs === 0
        ? 1
        : smoothstep(elapsed / fadeInMs)
      const recoveryWeight = elapsed <= active.duration || recoveryMs === 0
        ? 1
        : 1 - smoothstep((elapsed - active.duration) / recoveryMs)
      const motionWeight = Math.min(fadeInWeight, recoveryWeight)
      for (const [logicalParameter, value] of Object.entries(current)) {
        // Breath is a centered physical input (0.5 is neutral). Scale its
        // excursion around the neutral point so a low-intensity tail gesture
        // does not collapse the parameter toward zero.
        const scaledValue = logicalParameter === 'breath'
          ? 0.5 + (value - 0.5) * active.request.intensity
          : value * active.request.intensity
        contributions.push({
          logicalParameter,
          value: scaledValue,
          source: `motion:${preset.name}:${active.request.owner}`,
          priority: active.request.priority,
          weight: motionWeight,
        })
      }
    }
    if (!this.active.size) this.startNextQueued()
    return contributions
  }

  drainNativeContributions(): NativeMotionContribution[] {
    return this.nativeFrame.splice(0)
  }

  getDebugState() {
    const now = this.clock()
    const primary = this.primaryActive()
    const elapsed = primary ? now - primary.startedAt : 0
    return {
      state: this.state,
      motion: this.currentMotion,
      elapsedMs: Math.round(elapsed),
      durationMs: primary?.duration ?? 0,
      progress: primary?.duration ? Math.min(1, elapsed / primary.duration) : 0,
      queue: this.queue.map(item => item.name),
      activeRequests: [...this.active.values()].map(active => ({
        name: active.request.name,
        owner: active.request.owner,
        source: active.request.source,
        priority: active.request.priority,
        channels: [...active.request.channels],
        turnId: active.request.turnId ?? '',
        remainingMs: Number.isFinite(active.expiresAt)
          ? Math.max(0, Math.round(active.expiresAt - now))
          : null,
      })),
      native: this.nativePlayer?.getDebugState() ?? null,
      nativeFallbackReason: this.nativeFallbackReason,
    }
  }

  drainDueSteps(): SequenceStep[] {
    const now = this.clock()
    return [...this.active.values()].flatMap(active => {
      const elapsed = now - active.startedAt
      return (active.preset?.steps ?? []).filter((step, index) => {
        if (step.time > elapsed || active.executedSteps.has(index)) return false
        active.executedSteps.add(index)
        return true
      })
    })
  }

  private primaryActive(): ActiveMotion | undefined {
    return [...this.active.values()].sort((left, right) =>
      right.request.priority - left.request.priority
      || right.startedAt - left.startedAt)[0]
  }

  private startNextQueued(): void {
    const next = this.queue.shift()
    if (next) this.play(next.name, next.source, next.intensity)
  }
}

function inferChannels(preset: MotionPreset): MotionChannel[] {
  const channels = new Set<MotionChannel>()
  for (const frame of preset.keyframes) {
    if (frame.parameter.startsWith('head.')) channels.add('head')
    else if (frame.parameter.startsWith('body.')) channels.add('body')
    else if (frame.parameter.startsWith('eye.')) channels.add('gaze')
    else if (frame.parameter.startsWith('mouth.')) channels.add('mouth')
    else if (frame.parameter.startsWith('blink.')) channels.add('expression')
    else if (frame.parameter === 'breath' || frame.parameter.startsWith('tail.')) channels.add('tail')
    else channels.add('full')
  }
  return channels.size ? [...channels] : ['full']
}

function normalizeChannels(channels: MotionChannel[]): MotionChannel[] {
  return channels.includes('full') ? ['full'] : [...new Set(channels)]
}

function channelsOverlap(left: MotionChannel[], right: MotionChannel[]): boolean {
  return left.includes('full') || right.includes('full')
    || left.some(channel => right.includes(channel))
}

function sourcePriority(source: MotionSource): number {
  if (source === 'pet') return 60
  if (source === 'system') return 55
  if (source === 'ai') return 50
  return 10
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
