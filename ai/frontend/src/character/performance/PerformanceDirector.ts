import type { CharacterIntent } from '../CharacterBehaviorResolver.ts'
import type { MotionPrimitive } from '../MotionAction.ts'

export interface PerformanceDirectorOptions {
  audioWaitMs?: number
  repeatWindowMs?: number
}

interface StagedPerformance {
  turnId: string
  base: CharacterIntent
  segments: Array<Record<string, unknown>>
  stagedAt: number
}

interface AudioTiming {
  turnId: string
  startedAt: number
  durationMs: number
}

interface ScheduledCue {
  dueAt: number
  intent: CharacterIntent
}

/**
 * Turn-scoped semantic performance scheduler.
 *
 * It adopts Soullink's duration scheduling principle: LLM semantics are
 * aligned to the real decoded audio duration, while renderer parameters and
 * per-frame curves remain owned by the existing Live2D control chain.
 */
export class PerformanceDirector {
  private readonly now: () => number
  private readonly audioWaitMs: number
  private readonly repeatWindowMs: number
  private staged: StagedPerformance | null = null
  private audio: AudioTiming | null = null
  private cues: ScheduledCue[] = []
  private emittedCueCount = 0
  private readonly recentGestures = new Map<string, number>()

  constructor(
    now: () => number = () => performance.now(),
    options: PerformanceDirectorOptions = {},
  ) {
    this.now = now
    this.audioWaitMs = clamp(options.audioWaitMs ?? 240, 80, 800)
    this.repeatWindowMs = clamp(options.repeatWindowMs ?? 6_000, 0, 30_000)
  }

  stage(base: CharacterIntent, segments?: Array<Record<string, unknown>>): void {
    const turnId = base.turnId || ''
    this.staged = {
      turnId,
      base: { ...base, turnId },
      segments: segments?.length ? segments.map(segment => ({ ...segment })) : [],
      stagedAt: this.now(),
    }
    this.cues = []
    this.emittedCueCount = 0
    if (this.audio?.turnId === turnId) this.scheduleFromAudio(this.staged, this.audio)
    else this.scheduleFallback(this.staged)
  }

  onAudioStart(turnId: string, durationMs: number): void {
    this.audio = {
      turnId,
      startedAt: this.now(),
      durationMs: clamp(durationMs, 120, 120_000),
    }
    if (this.staged?.turnId === turnId) this.scheduleFromAudio(this.staged, this.audio)
  }

  onAudioEnd(turnId: string): void {
    if (this.audio?.turnId === turnId) this.audio = null
    if (this.staged?.turnId === turnId) this.cues = []
  }

  cancelTurn(turnId: string): void {
    if (this.audio?.turnId === turnId) this.audio = null
    if (this.staged?.turnId !== turnId) return
    this.staged = null
    this.cues = []
    this.emittedCueCount = 0
  }

  reset(): void {
    this.staged = null
    this.audio = null
    this.cues = []
    this.emittedCueCount = 0
    this.recentGestures.clear()
  }

  update(): CharacterIntent[] {
    const timestamp = this.now()
    const due: CharacterIntent[] = []
    while (this.cues.length && this.cues[0].dueAt <= timestamp) {
      const scheduled = this.cues.shift()!
      if (!this.staged || scheduled.intent.turnId !== this.staged.turnId) continue
      this.emittedCueCount += 1
      due.push(this.suppressRepeatedGesture(
        withLocalSemanticGesture(scheduled.intent),
        timestamp,
      ))
    }
    return due
  }

  getDebugState(): Record<string, unknown> {
    return {
      turnId: this.staged?.turnId ?? null,
      audio: this.audio ? { ...this.audio } : null,
      pendingCues: this.cues.map(cue => ({
        dueAt: cue.dueAt,
        emotion: cue.intent.emotion,
        behavior: cue.intent.behavior,
        hasMotionPlan: Boolean(cue.intent.motionPlan),
      })),
      emittedCueCount: this.emittedCueCount,
      recentGestureCount: this.recentGestures.size,
    }
  }

  private scheduleFallback(staged: StagedPerformance): void {
    const intents = this.buildIntents(staged)
    let dueAt = staged.stagedAt + this.audioWaitMs
    this.cues = intents.map((intent, index) => {
      const cue = { dueAt, intent }
      if (index < intents.length - 1) dueAt += estimateSegmentMs(staged.segments[index])
      return cue
    })
  }

  private scheduleFromAudio(staged: StagedPerformance, audio: AudioTiming): void {
    const intents = this.buildIntents(staged)
    const weights = intents.map((_, index) => segmentWeight(staged.segments[index]))
    const totalWeight = weights.reduce((sum, value) => sum + value, 0) || 1
    let elapsedWeight = 0
    this.cues = intents.map((intent, index) => {
      const dueAt = audio.startedAt + audio.durationMs * elapsedWeight / totalWeight
      elapsedWeight += weights[index]
      return { dueAt, intent }
    }).slice(this.emittedCueCount)
  }

  private buildIntents(staged: StagedPerformance): CharacterIntent[] {
    if (!staged.segments.length) return [{ ...staged.base }]
    return staged.segments.map((segment, index) => ({
      ...staged.base,
      ...segment,
      turnId: staged.turnId,
      motionPlan: segment.motionPlan ?? (index === 0 ? staged.base.motionPlan : undefined),
    } as CharacterIntent))
  }

  private suppressRepeatedGesture(intent: CharacterIntent, timestamp: number): CharacterIntent {
    if (!intent.motionPlan) return intent
    const signature = motionSignature(intent.motionPlan)
    if (!signature) return { ...intent, motionPlan: undefined }
    const previous = this.recentGestures.get(signature) ?? -Infinity
    this.pruneRecentGestures(timestamp)
    if (timestamp - previous < this.repeatWindowMs) return { ...intent, motionPlan: undefined }
    this.recentGestures.set(signature, timestamp)
    return intent
  }

  private pruneRecentGestures(timestamp: number): void {
    for (const [signature, acceptedAt] of this.recentGestures) {
      if (timestamp - acceptedAt >= this.repeatWindowMs) this.recentGestures.delete(signature)
    }
  }
}

function motionSignature(value: unknown): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  const steps = (value as Record<string, unknown>).steps
  if (!Array.isArray(steps)) return ''
  return steps.map(step => {
    if (!step || typeof step !== 'object') return ''
    const record = step as Record<string, unknown>
    return `${String(record.primitive ?? '')}:${Math.round(Number(record.intensity ?? 0) * 4)}`
  }).filter(Boolean).join('|')
}

function withLocalSemanticGesture(intent: CharacterIntent): CharacterIntent {
  if (intent.motionPlan || intent.behavior !== 'speak') return intent
  const emotion = (intent.emotion || 'neutral').toLowerCase()
  const recipes: Record<string, MotionPrimitive[]> = {
    happy: ['tilt_left', 'tilt_right', 'nod'],
    playful: ['tilt_right', 'nod', 'tilt_left'],
    joyful: ['nod', 'tilt_left', 'tilt_right'],
    cheerful: ['nod', 'tilt_right', 'tilt_left'],
    surprised: ['lean_back', 'tilt_left'],
    shy: ['tilt_left', 'tilt_right'],
    embarrassed: ['tilt_right', 'tilt_left'],
    sad: ['lean_forward', 'tilt_left'],
    worried: ['lean_forward', 'tilt_right'],
    angry: ['lean_forward', 'nod'],
  }
  const candidates = recipes[emotion]
  if (!candidates || (intent.intensity ?? 0.5) < 0.32) return intent
  const hash = [...(intent.turnId || emotion)]
    .reduce((value, character) => ((value * 31) + character.charCodeAt(0)) >>> 0, 7)
  const primitive = candidates[hash % candidates.length]
  const intensity = clamp(
    (intent.intensity ?? 0.5) * 0.55 + (intent.energy ?? 0.5) * 0.18,
    0.25,
    0.55,
  )
  return {
    ...intent,
    motionPlan: {
      durationMs: 900,
      steps: [{ atMs: 40, durationMs: 720, primitive, intensity }],
    },
  }
}

function segmentWeight(segment: Record<string, unknown> | undefined): number {
  const text = typeof segment?.text === 'string' ? segment.text.trim() : ''
  return Math.max(1, Math.sqrt(Math.max(1, [...text].length)))
}

function estimateSegmentMs(segment: Record<string, unknown> | undefined): number {
  const explicit = typeof segment?.durationMs === 'number' ? segment.durationMs : NaN
  if (Number.isFinite(explicit)) return clamp(explicit, 300, 4_000)
  const text = typeof segment?.text === 'string' ? [...segment.text].length : 8
  return clamp(320 + text * 95, 500, 3_200)
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
