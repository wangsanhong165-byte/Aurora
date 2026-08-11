import type {
  AvatarPerformanceCapabilities,
  CharacterPerformancePersonality,
} from '../AvatarCapabilityProfile.ts'
import { IdleBehaviorController, type IdleBehaviorSnapshot } from '../IdleBehaviorController.ts'
import { facsFromVAD, logicalFaceFromFACS } from './FACSState.ts'
import { resolveMotionStyle, type MotionStyleOptions, type ResolvedMotionStyle } from './MotionStyle.ts'
import { SpeechPerformanceController } from './SpeechPerformanceController.ts'
import type { VADVector } from './VADState.ts'
import { semanticPostureFromVAD } from './SemanticPosture.ts'
import { VoiceWaitingMotionController } from './VoiceWaitingMotionController.ts'

export type AmbientPerformanceChannel = 'head' | 'body' | 'gaze'

export interface AmbientPerformanceInput {
  vad: VADVector
  audioLevel: number
  enabled: boolean
  blockedChannels: ReadonlySet<AmbientPerformanceChannel>
  tracking?: Record<string, number>
  focusWeights?: { head: number; body: number; gaze: number }
  gain?: number
}

export interface AmbientPerformanceFrame {
  values: Record<string, number>
  faceValues: Record<string, number>
  eyeClose: number
  idle: IdleBehaviorSnapshot
  activity: string
}

/**
 * Deep module for ambient character performance.
 *
 * Exactly one activity generator supplies the base rhythm at a time. VAD
 * posture, activity transitions, capability filtering and motion ownership
 * are resolved here so callers submit one coherent pose layer to the mixer.
 */
export class AmbientPerformanceEngine {
  private readonly idle = new IdleBehaviorController()
  private readonly speech = new SpeechPerformanceController()
  private readonly waiting: VoiceWaitingMotionController
  private style: ResolvedMotionStyle
  private activity = 'idle'
  private current: Record<string, number> = {}
  private eyeClose = 0
  private enhanced = true

  constructor(seed = 1) {
    this.style = resolveMotionStyle({ seed })
    this.waiting = new VoiceWaitingMotionController(seed)
  }

  configure(
    options: MotionStyleOptions | undefined,
    personality?: CharacterPerformancePersonality,
    capabilities?: AvatarPerformanceCapabilities,
  ): void {
    this.style = resolveMotionStyle(options)
    this.idle.setMotionStyle({ ...options, seed: this.style.seed }, personality, capabilities)
    this.speech.configure(this.style)
    this.reset()
  }

  setActivity(activity: string): void {
    this.activity = activity
    this.speech.setSpeaking(activity === 'speaking')
  }

  setLegacy(enabled: boolean): void {
    this.enhanced = !enabled
    this.idle.setLegacy(enabled)
  }

  reset(): void {
    this.current = {}
    this.eyeClose = 0
    this.idle.reset()
    this.speech.reset()
    this.speech.setSpeaking(this.activity === 'speaking')
    this.waiting.reset()
  }

  update(dt: number, input: AmbientPerformanceInput): AmbientPerformanceFrame {
    const delta = Math.max(0, Math.min(0.1, dt))
    const gain = Math.max(0, Math.min(2.5, input.gain ?? 1))
    const idleAllowed = input.enabled
      && this.activity === 'idle'
    this.idle.setVAD(input.vad)
    this.idle.update(delta, idleAllowed, input.focusWeights)
    const idle = this.idle.getSnapshot()
    const speech = this.speech.update(delta, input.audioLevel)
    const waiting = this.waiting.update(
      delta,
      input.enabled && this.enhanced ? this.activity : 'idle',
      gain,
    )

    let target: Record<string, number> = {}
    if (input.enabled) {
      if (this.activity === 'idle') target = logicalIdlePose(idle, gain)
      else if (this.activity === 'speaking') target = logicalSpeechPose(speech, gain)
      else if (this.activity === 'listening' || this.activity === 'thinking') target = waiting
    }
    if (input.enabled && this.enhanced) target = addLogical(target, vadPosture(input.vad, gain))
    target = filterChannels(target, input.blockedChannels)
    this.current = approachPose(this.current, target, delta)
    // Tracking already owns a hierarchical response model (eyes -> head ->
    // torso). Filtering it again here recreates the slow, smooth stiffness
    // this engine is intended to avoid.
    const tracking = input.enabled && input.tracking
      ? filterChannels(input.tracking, input.blockedChannels)
      : {}
    const resolvedPose = addLogical(this.current, tracking)

    const eyeCloseTarget = idleAllowed && !input.blockedChannels.has('gaze')
      ? idle.eyeClose * gain
      : 0
    const eyeResponse = 1 - Math.exp(-delta * (eyeCloseTarget > this.eyeClose ? 12 : 7))
    this.eyeClose += (eyeCloseTarget - this.eyeClose) * eyeResponse

    const facs = facsFromVAD(input.vad)
    return {
      values: filterChannels(resolvedPose, input.blockedChannels),
      faceValues: this.enhanced ? logicalFaceFromFACS(facs) : {},
      eyeClose: this.eyeClose,
      idle,
      activity: this.activity,
    }
  }
}

function logicalIdlePose(snapshot: IdleBehaviorSnapshot, gain: number): Record<string, number> {
  return {
    'head.x': snapshot.headX * gain,
    'head.y': snapshot.headY * gain,
    'head.z': snapshot.headZ * gain,
    'eye.x': snapshot.eyeX * gain,
    'eye.y': snapshot.eyeY * gain,
    'body.x': snapshot.bodyX * gain,
    'body.y': snapshot.bodyY * gain,
  }
}

function logicalSpeechPose(
  sample: ReturnType<SpeechPerformanceController['update']>,
  gain: number,
): Record<string, number> {
  return {
    'head.x': sample.headX * gain,
    'head.y': sample.headY * gain,
    'head.z': sample.headZ * gain,
    'body.x': sample.bodyX * gain,
    'body.y': sample.bodyY * gain,
  }
}

function vadPosture(vad: VADVector, gain: number): Record<string, number> {
  return semanticPostureFromVAD(vad, gain)
}

function addLogical(
  base: Record<string, number>,
  addition: Record<string, number>,
): Record<string, number> {
  const result = { ...base }
  for (const [key, value] of Object.entries(addition)) result[key] = (result[key] ?? 0) + value
  return result
}

function approachPose(
  current: Record<string, number>,
  target: Record<string, number>,
  dt: number,
): Record<string, number> {
  const result: Record<string, number> = {}
  for (const key of new Set([...Object.keys(current), ...Object.keys(target)])) {
    const from = current[key] ?? 0
    const to = target[key] ?? 0
    const response = 1 - Math.exp(-dt * (Math.abs(to) > Math.abs(from) ? 5.2 : 3.8))
    const value = from + (to - from) * response
    if (Math.abs(value) > 0.0001 || key in target) result[key] = value
  }
  return result
}

function filterChannels(
  values: Record<string, number>,
  blocked: ReadonlySet<AmbientPerformanceChannel>,
): Record<string, number> {
  return Object.fromEntries(Object.entries(values).filter(([key]) => {
    if (key.startsWith('head.')) return !blocked.has('head')
    if (key.startsWith('body.')) return !blocked.has('body')
    if (key.startsWith('eye.')) return !blocked.has('gaze')
    return true
  }))
}
