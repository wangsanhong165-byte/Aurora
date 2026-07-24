import type {
  AvatarPerformanceCapabilities,
  CharacterPerformancePersonality,
} from './AvatarCapabilityProfile'
import { BodySwayController } from './performance/BodySwayController'
import { IdleActionScheduler, type IdleActionLabel } from './performance/IdleActionScheduler'
import { deriveMotionSeed, resolveMotionStyle, type MotionStyleOptions } from './performance/MotionStyle'
import type { VADVector } from './performance/VADState'

export interface IdleBehaviorSnapshot {
  headX: number
  headY: number
  headZ: number
  eyeX: number
  eyeY: number
  bodyX: number
  bodyY: number
  eyeClose: number
  activeAction: IdleActionLabel | null
  actionProgress: number
  energy: number
  transitionProgress: number
}

export class IdleBehaviorController {
  private _elapsedMs = 0
  private _phase = Math.random() * Math.PI * 2
  private _style = resolveMotionStyle()
  private _bodySway = new BodySwayController(deriveMotionSeed(this._style.seed, 5))
  private _actions = new IdleActionScheduler(
    deriveMotionSeed(this._style.seed, 6),
    this._style.spontaneity,
    this._style.idleActionGain,
    this._style.avoidRepeatWindow,
  )
  private _personality: CharacterPerformancePersonality | undefined
  private _capabilities: AvatarPerformanceCapabilities | undefined
  private _vad: VADVector = { valence: 0, arousal: 0, dominance: 0 }
  private _snapshot: IdleBehaviorSnapshot = {
    headX: 0, headY: 0, headZ: 0, eyeX: 0, eyeY: 0,
    bodyX: 0, bodyY: 0, eyeClose: 0,
    activeAction: null, actionProgress: 0,
    energy: 0.22, transitionProgress: 0,
  }

  reset(): void {
    this._elapsedMs = 0
    this._snapshot.transitionProgress = 0
    this._bodySway.reset(deriveMotionSeed(this._style.seed, 5))
  }

  setMotionStyle(
    options: MotionStyleOptions | undefined,
    personality?: CharacterPerformancePersonality,
    capabilities?: AvatarPerformanceCapabilities,
  ): void {
    this._style = resolveMotionStyle(options)
    this._personality = personality
    this._capabilities = capabilities
    this._actions = new IdleActionScheduler(
      deriveMotionSeed(this._style.seed, 6),
      this._style.spontaneity,
      this._style.idleActionGain,
      this._style.avoidRepeatWindow,
    )
    this.reset()
  }

  setVAD(vad: VADVector): void {
    this._vad = { ...vad }
  }

  update(dt: number, allowed: boolean): void {
    this._elapsedMs += dt * 1000
    const seconds = this._elapsedMs / 1000
    const targetWeight = allowed ? 1 : 0
    const blend = 1 - Math.exp(-dt * (allowed ? 1.8 : 4.5))
    const weight = this._snapshot.transitionProgress
      + (targetWeight - this._snapshot.transitionProgress) * blend
    const sway = this._bodySway.update(seconds, allowed ? 0 : 1, this._style.bodyMotionGain)
    const action = this._actions.update(seconds, {
      allowed,
      focusLevel: allowed ? 0 : 1,
      capabilities: this._capabilities,
      personality: this._personality,
      vad: this._vad,
    })
    const actionState = this._actions.getState()
    this._snapshot = {
      headX: (sway.headX + action.headX + Math.sin(seconds * 0.29 + this._phase) * 0.18) * weight,
      headY: (sway.headY + action.headY + Math.sin(seconds * 0.21 + 1.2) * 0.12) * weight,
      headZ: (sway.headZ + action.headZ + Math.sin(seconds * 0.17 + 0.4) * 0.12) * weight,
      eyeX: (Math.sin(seconds * 0.13 + 2.1) * 0.18 + action.eyeX) * weight,
      eyeY: (Math.sin(seconds * 0.09 + 0.8) * 0.1 + action.eyeY) * weight,
      bodyX: (sway.bodyX + action.bodyX) * weight,
      bodyY: (sway.bodyY + action.bodyY) * weight,
      eyeClose: action.eyeClose * weight,
      activeAction: actionState.activeAction,
      actionProgress: actionState.progress,
      energy: 0.22 * weight,
      transitionProgress: weight,
    }
  }

  getSnapshot(): IdleBehaviorSnapshot { return { ...this._snapshot } }
}
