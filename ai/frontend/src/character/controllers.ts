// Character Controller — coordinates Live2D subsystems
// All parameter writes go through ParameterMixer → Live2DModelAdapter.
// No business controller may hold CubismModelHandle directly.

import { eventBus } from '../core/event-bus'
import { isPerFrameGazeLoggingEnabled } from './performance-policy'
import { getExpression } from './live2d/expression'
import { ExpressionController } from './ExpressionController'
import { MotionArbiter } from './MotionArbiter'
import { CharacterBehaviorResolver, type CharacterBehaviorConfig } from './CharacterBehaviorResolver'
import { CharacterPerformancePolicy } from './CharacterPerformancePolicy'
import { IdleBehaviorController } from './IdleBehaviorController'
import type { AvatarCapabilityProfile } from './AvatarCapabilityProfile'
import { AvatarParameterResolver } from './AvatarParameterResolver'
import { ParameterMixer } from './ParameterMixer'
import { AudioAnalyzer } from './AudioAnalyzer'
import { SpeechPerformanceController } from './performance/SpeechPerformanceController'
import { resolveMotionStyle } from './performance/MotionStyle'
import { VADState } from './performance/VADState'
import { facsFromVAD } from './performance/FACSState'
import { VADMicroMotionController } from './performance/VADMicroMotionController'
import { VADGestureController } from './performance/VADGestureController'
import { PrivateEmotionOverlay } from './performance/PrivateEmotionOverlay'
import { VoiceWaitingMotionController } from './performance/VoiceWaitingMotionController'
import type { PerformanceMode } from './AvatarCapabilityProfile'
import type { NativeMotionPlayer } from './live2d/NativeMotionPlayer'
import type { Live2DModelAdapter } from './Live2DModelAdapter'
import { InteractionPerformancePolicy } from './performance/InteractionPerformancePolicy'
import { CharacterStateMachine, type CharacterActivity } from './CharacterStateMachine'

// ── Parameter Interpolation (smooth transitions) ──

interface ParamTarget {
  id: string
  from: number
  to: number
  startTime: number
  duration: number
}

export function expressionTargetForBlend(
  value: number,
  intensity: number,
  blend: 'add' | 'multiply' | 'overwrite' = 'add',
  current = 0,
): number {
  const weight = Math.max(0, Math.min(1, intensity))
  if (blend === 'multiply') return 1 + (value - 1) * weight
  if (blend === 'overwrite') return current + (value - current) * weight
  return value * weight
}

export class ParameterController {
  private mixer: ParameterMixer | null = null
  private targets: ParamTarget[] = []
  private defaultParams = new Map<string, number>()
  // Expressions must keep contributing after their transition finishes.
  // ParameterMixer intentionally clears frame values every animation frame.
  private activeExpressionParams = new Set<string>()
  // Track part IDs from the current expression's part opacity changes
  private activeExpressionParts = new Set<string>()
  // Track last applied value for each parameter (used as interpolation "from")
  private _currentValues = new Map<string, number>()

  attach(_adapter: Live2DModelAdapter, mixer: ParameterMixer): void {
    this.mixer = mixer
    this._currentValues.clear()
    this.activeExpressionParams.clear()
  }

  detach(): void {
    this.mixer = null
    this.targets = []
    this._currentValues.clear()
    this.activeExpressionParams.clear()
  }

  /** Set a tracked current value. */
  private _setTracked(id: string, value: number): void {
    this._currentValues.set(id, value)
  }

  /** Get tracked current value (fallback to 0). */
  private _getTracked(id: string): number {
    return this._currentValues.get(id) ?? 0
  }

  /** Queue a smooth parameter transition.
   *  The interpolated values are later submitted to the mixer via getContributions(). */
  setSmooth(id: string, to: number, duration = 300, delay = 0): void {
    const from = this._getTracked(id)
    this.removeTargets(id)
    this.targets.push({ id, from, to, startTime: performance.now() + delay, duration })
  }

  /** Remove any pending interpolation targets for the given parameter id(s). */
  removeTargets(ids: string | string[]): void {
    const removeSet = new Set(typeof ids === 'string' ? [ids] : ids)
    this.targets = this.targets.filter(t => !removeSet.has(t.id))
  }

  /** Count active targets for a given param. */
  getTargetCount(id: string): number {
    return this.targets.filter(t => t.id === id).length
  }

  /** Get all param IDs with active interpolation targets. */
  getActiveTargetParams(): Set<string> {
    return new Set(this.targets.map(t => t.id))
  }

  /** Apply expression preset with smooth transition. */
  applyExpression(name: string, intensity: number, duration = 400): void {
    const preset = getExpression(name)
    const pIntensity = Math.max(0, Math.min(1, intensity))
    const nextIds = new Set(preset.params.map((p) => p.id))

    // Release controls owned by the prior expression but absent from this one.
    for (const id of this.activeExpressionParams) {
      if (!nextIds.has(id)) this.setSmooth(id, 0, duration)
    }
    this.activeExpressionParams = nextIds

    for (const p of preset.params) {
      const value = expressionTargetForBlend(
        p.value,
        pIntensity,
        p.blend,
        this._getTracked(p.id),
      )
      if (!this.defaultParams.has(p.id)) {
        this.defaultParams.set(p.id, value)
      }
      this.setSmooth(p.id, value, duration)
    }

    // Part opacity changes follow the same adapter-owned write path as parameters.
    // Always clear old expression parts first, even if the new expression has none.
    const nextPartIds = preset.parts ? new Set(preset.parts.map((p) => p.id)) : new Set<string>()
    if (this.mixer) {
      for (const partId of this.activeExpressionParts) {
        if (!nextPartIds.has(partId)) {
          this.mixer.submitPartOpacity({
            id: `expression-part:${partId}`,
            partId,
            opacity: 0,
            priority: 75,
          })
        }
      }
    }
    this.activeExpressionParts = nextPartIds
    if (preset.parts && this.mixer) {
      for (const part of preset.parts) {
        this.mixer.submitPartOpacity({
          id: `expression-part:${part.id}`,
          partId: part.id,
          opacity: part.opacity * pIntensity,
          priority: 75,
        })
      }
    }
  }

  /** Reset to neutral with transition. */
  resetToNeutral(duration = 500): void {
    this.applyExpression('neutral', 1, duration)
  }

  /**
   * Update active interpolations and return contributions for the mixer.
   * Call each frame. The returned contributions should be submitted to
   * ParameterMixer before resolve/apply.
   */
  update(): Array<{ parameterId: string; value: number; source: string; priority: number }> {
    const now = performance.now()
    this.targets = this.targets.filter((t) => {
      const elapsed = now - t.startTime
      const progress = Math.min(1, elapsed / t.duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      const value = t.from + (t.to - t.from) * eased
      this._setTracked(t.id, value)

      return progress < 1
    })

    // Return the settled values as well as values still interpolating. Without
    // this, expressions disappear on the first frame after their fade-in.
    return [...this.activeExpressionParams].map((parameterId) => ({
      parameterId,
      value: this._getTracked(parameterId),
      source: 'expression',
      priority: 75,
    }))
  }
}

// ── Idle Animation (blink + breath) ──

export class IdleController {
  constructor(private readonly parameters: AvatarParameterResolver) {}
  private time = 0
  private breathing = true
  private breathWeight = 1
  private breathTarget = 1
  private blinking = true
  private idleEnabled = true
  private nextBlink = 0
  private blinkState = 0
  private blinkPhase = 0
  private _eyeOpenValue = 1
  private _blinkBreathValue = 0.5
  private static readonly BASE_BLINK_INTERVAL = 2.8
  private static readonly BLINK_VARIATION = 0.6
  private static readonly BREATH_FREQ = 1.7
  private blinkRate = 1
  private breathRate = 1
  private breathVariance = 0.42

  setTiming(blinkRate = 1, breathRate = 1, breathVariance = 0.42): void {
    this.blinkRate = Math.max(0.25, Math.min(2.5, blinkRate))
    this.breathRate = Math.max(0.5, Math.min(1.8, breathRate))
    this.breathVariance = Math.max(0, Math.min(1, breathVariance))
  }

  private _breathBodyX = 0
  private _breathBodyY = 0

  attach(): void {
    this.time = 0
    this.nextBlink = IdleController.BASE_BLINK_INTERVAL
      * (0.72 + Math.random() * IdleController.BLINK_VARIATION * this.breathVariance)
      / this.blinkRate
  }

  detach(): void {
    // nothing to clean up — no handle reference
  }

  setBreathing(enabled: boolean): void {
    this.breathing = enabled
    this.breathTarget = enabled ? 1 : 0.35
  }

  setBlinking(enabled: boolean): void {
    this.blinking = enabled
    if (!enabled) { this._eyeOpenValue = 1 }
  }

  setIdleEnabled(enabled: boolean): void {
    this.idleEnabled = enabled
    if (!enabled) { this._breathBodyX = 0; this._breathBodyY = 0; this._eyeOpenValue = 1; this._blinkBreathValue = 0.5 }
  }

  getBreathBodyX(): number { return this._breathBodyX }
  getBreathBodyY(): number { return this._breathBodyY }

  getBlinkParams(externalEyeClose = 0): Record<string, number> {
    const eyeOpen = Math.min(this._eyeOpenValue, 1 - Math.max(0, Math.min(1, externalEyeClose)))
    return this.parameters.values({ 'blink.left': eyeOpen, 'blink.right': eyeOpen })
  }

  getBreathParams(): Record<string, number> {
    const breath = Math.sin(this.time * IdleController.BREATH_FREQ)
    return this.parameters.values({
      'body.x': breath * 0.7 * this.breathWeight,
      'body.y': breath * 1.2 * this.breathWeight,
      breath: this._blinkBreathValue,
    })
  }

  update(dt: number): void {
    if (!this.idleEnabled) return
    this.time += dt
    this.breathWeight += (this.breathTarget - this.breathWeight)
      * (1 - Math.exp(-dt * 3.5))

    if (this.breathing || this.breathWeight > 0.01) {
      const breath = Math.sin(this.time * IdleController.BREATH_FREQ * this.breathRate)
      this._breathBodyX = breath * 0.7 * this.breathWeight
      this._breathBodyY = breath * 1.2 * this.breathWeight
      this._blinkBreathValue = 0.5 + breath * 0.18 * this.breathWeight
    }

    if (!this.blinking) return
    if (this.time >= this.nextBlink && this.blinkState === 0) {
      this.blinkState = 1
      this.blinkPhase = 0
    }

    if (this.blinkState > 0) {
      this.blinkPhase += dt * 15
      if (this.blinkState === 1) {
        this._eyeOpenValue = Math.max(0, 1 - this.blinkPhase)
        if (this._eyeOpenValue <= 0) {
          this.blinkState = 2
          this.blinkPhase = 0
        }
      } else {
        this._eyeOpenValue = Math.min(1, this.blinkPhase)
        if (this._eyeOpenValue >= 1) {
          this.blinkState = 0
          this._eyeOpenValue = 1
          this.nextBlink = this.time + IdleController.BASE_BLINK_INTERVAL
            * (0.72 + Math.random() * IdleController.BLINK_VARIATION * this.breathVariance)
            / this.blinkRate
        }
      }
    }
  }
}

// ── Character Controller (top-level coordinator) ──

const MODEL_PARAM_CONFIG: Record<string, {
  angleXSign: number
  angleYSign: number
  eyeBallYSign: number
}> = {
  'Design_genius_White': { angleXSign: 1, angleYSign: 1, eyeBallYSign: 1 },
  'youxiaomiao':         { angleXSign: 1, angleYSign: 1, eyeBallYSign: 1 },
  'ariu':                { angleXSign: 1, angleYSign: 1, eyeBallYSign: 1 },
  'mao_zh-Hans':         { angleXSign: 1, angleYSign: 1, eyeBallYSign: 1 },
}

function getModelParamConfig(modelName: string) {
  return MODEL_PARAM_CONFIG[modelName] ?? MODEL_PARAM_CONFIG['Design_genius_White']
}

export class CharacterController {
  paramCtrl = new ParameterController()
  parameterResolver = new AvatarParameterResolver()
  idleCtrl = new IdleController(this.parameterResolver)
  exprCtrl = new ExpressionController(this.paramCtrl)
  motionArbiter = new MotionArbiter()
  behaviorResolver = new CharacterBehaviorResolver()
  performancePolicy = new CharacterPerformancePolicy()
  idleBehavior = new IdleBehaviorController()
  mixer = new ParameterMixer()
  audioAnalyzer = new AudioAnalyzer()
  speechPerformance = new SpeechPerformanceController()
  vad = new VADState()
  interactionPolicy = new InteractionPerformancePolicy()
  vadMicroMotion = new VADMicroMotionController()
  vadGesture = new VADGestureController()
  privateEmotion = new PrivateEmotionOverlay()
  voiceWaiting = new VoiceWaitingMotionController()
  stateMachine = new CharacterStateMachine()

  // References set externally by the animation loop
  private adapter: Live2DModelAdapter | null = null
  private cleanupFns: (() => void)[] = []
  private get currentActivity(): string {
    return this.stateMachine.activity
  }
  private previousActivity = 'idle'
  private activityEnteredAt = performance.now()
  private activityBlend = 0
  private speechWeight = 0
  private audioPlaybackActive = false
  private lastDebugEmitAt = 0
  private headTrackingEnabled = true
  private _modelName = 'Design_genius_White'
  private _profile: AvatarCapabilityProfile | undefined
  private _style = resolveMotionStyle()
  private _performanceMode: PerformanceMode = 'enhanced'
  private _parameterGain = 1.45
  private _bodyMotionGain = 1.25
  private _currentEmotion = 'neutral'
  private _currentEmotionIntensity = 0
  private _nativeExpressions: string[] = []
  private _nativeMotions: string[] = []
  private _performanceResetTimer: ReturnType<typeof setTimeout> | null = null

  // Mouse tracking state
  private mouseX = 0
  private mouseY = 0
  private targetMouseX = 0
  private targetMouseY = 0
  private headX = 0
  private headY = 0
  private idleTime = 0

  // Tracks motion arbiter transitions for idle restart guard
  private _wasPlaying = false
  private _lastMotionEnded = false

  // Lip-sync mouth value from AudioAnalyzer (submitted to mixer)
  private _mouthOpenValue = 0

  // Accessory state
  private _accessoryParts: Record<string, string> = {}
  private _accessoryState: Record<string, boolean> = {}
  private _onAccessoryChange: ((label: string, enabled: boolean) => void) | null = null

  setModelName(name: string, modelExpressionNames: string[] = []): void {
    this._modelName = name
    const configs = (window as any).__INITIAL_MODEL_INFO__?.behaviorConfig as Record<string, CharacterBehaviorConfig> | undefined
    const config = configs?.[name]
    const profiles = (window as any).__INITIAL_MODEL_INFO__?.avatarProfiles as Record<string, AvatarCapabilityProfile> | undefined
    this._profile = profiles?.[name]
    this.parameterResolver.setProfile(this._profile)
    this.idleBehavior.setMotionStyle(
      this._profile?.motionStyle,
      this._profile?.personality,
      this._profile?.capabilities,
    )
    this._style = resolveMotionStyle(this._profile?.motionStyle)
    this.speechPerformance.configure(this._style)
    this.idleCtrl.setTiming(this._style.blinkRate, this._style.breathRate, this._style.breathVariance)
    this._performanceMode = this._profile?.performanceMode ?? 'enhanced'
    this.idleBehavior.setLegacy(this._performanceMode === 'legacy')
    this._parameterGain = this._profile?.parameterGain ?? 1.45
    this._bodyMotionGain = this._profile?.bodyMotionGain ?? 1.25
    this.applyOutputGains()
    const motionPresets = (window as any).__INITIAL_MODEL_INFO__?.motionPresets
    this.motionArbiter.setPresets(motionPresets)
    this.behaviorResolver.setConfig(config)
    this.exprCtrl.setModelConfig(
      { ...(config?.emotionMap ?? {}), ...(this._profile?.expressionMap ?? {}) },
      modelExpressionNames,
    )
    this._nativeExpressions = modelExpressionNames
    this.emitNativeCatalog()
  }

  setNativeMotionPlayer(player: NativeMotionPlayer | null): void {
    this.motionArbiter.setNativeMotionPlayer(player, this._profile?.motionMap)
    this._nativeMotions = player?.list() ?? []
    this.emitNativeCatalog()
    this.startNativeIdleIfAvailable()
  }

  /** Set the adapter reference and attach sub-controllers. */
  attach(adapter: Live2DModelAdapter): void {
    this.adapter = adapter
    this.paramCtrl.attach(adapter, this.mixer)
    this.idleCtrl.attach()
    this.audioAnalyzer.reset()
    this.speechPerformance.reset()

    // Register mixer owners with priorities
    const ids = (...keys: string[]) => keys.map(key => this.parameterResolver.resolve(key)).filter((id): id is string => Boolean(id))
    this.mixer.registerOwner('gaze', ids('head.x', 'head.y', 'head.z', 'eye.x', 'eye.y', 'body.x', 'body.y'), 30)
    this.mixer.registerOwner('blink', ids('blink.left', 'blink.right'), 40)
    this.mixer.registerOwner('breath', ids('breath', 'body.x', 'body.y'), 20)
    this.mixer.registerOwner('lip_sync', ids('mouth.open'), 60)
    this.mixer.registerOwner('idle_sway', ids('head.x', 'head.y', 'head.z'), 10)

    // Subscribe to event bus
    this.cleanupFns.push(
      eventBus.on('character:emotion', ({ emotion, intensity }) => {
        this.applyIntent({ emotion, intensity })
      }),
    )

    this.cleanupFns.push(
      eventBus.on('character:intent', ({ emotion, behavior, intensity }) => {
        this.applyIntent({ emotion, behavior, intensity })
      }),
    )

    this.cleanupFns.push(
      eventBus.on('character:interaction', (interaction) => {
        const decision = this.interactionPolicy.resolve(interaction)
        if (decision) this.applyIntent(decision.intent)
      }),
    )

    this.cleanupFns.push(
      eventBus.on('character:performance_tuning', ({ mode, parameterGain, bodyMotionGain }) => {
        if (mode) this._performanceMode = mode
        if (parameterGain !== undefined) this._parameterGain = parameterGain
        if (bodyMotionGain !== undefined) this._bodyMotionGain = bodyMotionGain
        this.idleBehavior.setLegacy(this._performanceMode === 'legacy')
        this.applyOutputGains()
      }),
    )

    this.cleanupFns.push(
      eventBus.on('character:native_preview', ({ type, name }) => {
        if (type === 'motion') this.motionArbiter.play(name, 'system', 0.8)
        else this.exprCtrl.apply(name, 0.9, 180)
      }),
    )

    this.cleanupFns.push(
      eventBus.on('character:activity', ({ activity }) => {
        this.onActivityChange(activity)
      }),
    )

    this.cleanupFns.push(
      eventBus.on('audio:stop', () => {
        this.audioPlaybackActive = false
        this.audioAnalyzer.reset()
        this._mouthOpenValue = 0
      }),
    )

    this.cleanupFns.push(
      eventBus.on('audio:start', () => {
        this.audioPlaybackActive = true
        this.onActivityChange('speaking')
      }),
    )

    let audioEndTimer: ReturnType<typeof setTimeout> | null = null
    this.cleanupFns.push(
      eventBus.on('audio:end', () => {
        this.audioPlaybackActive = false
        this.audioAnalyzer.reset()
        this._mouthOpenValue = 0
        if (this.currentActivity === 'speaking') {
          if (audioEndTimer) clearTimeout(audioEndTimer)
          audioEndTimer = setTimeout(() => {
            if (!this.audioPlaybackActive) {
              this.onActivityChange('idle')
            }
          }, 400)
        }
      }),
    )

    this.cleanupFns.push(
      eventBus.on('audio:volume', ({ volume }) => {
        this._mouthOpenValue = this.audioAnalyzer.analyze(volume)
      }),
    )

    this.cleanupFns.push(
      eventBus.on('runtime:user_message', ({ text: _text }) => {
        this.onActivityChange('listening')
        this.applyIntent({ emotion: 'neutral', behavior: 'listen', intensity: 0.35, attention: 'user', energy: 0.25 })
        setTimeout(() => { if (this.stateMachine.activity === 'listening') this.onActivityChange('thinking') }, 350)
      }),
    )

    this.cleanupFns.push(
      eventBus.on('runtime:character_intent', ({ emotion, behavior, attention, energy, intensity, durationMs, naturalVAD, contextTags }) => {
        this.applyIntent({ emotion, behavior, attention: attention as any, energy, intensity, durationMs, naturalVAD, contextTags })
      }),
    )
  }

  /** Set the current turnId for stale event rejection. */
  setTurnId(turnId: string): void {
    this.stateMachine.force(this.stateMachine.activity, turnId)
  }

  private onActivityChange(activity: string, turnId = ''): void {
    if (activity === 'idle' && this.audioPlaybackActive) return
    if (!activity || activity === this.currentActivity) return
    // Reject stale events from previous turns
    if (turnId && !this.stateMachine.isCurrentTurn(turnId)) {
      eventBus.emit('character:runtime-telemetry', { type: 'runtime.stale-event-rejected', metadata: { turnId, currentTurnId: this.stateMachine.turnId, activity } })
      return
    }
    const from = this.stateMachine.activity
    const to = activity as CharacterActivity
    if (!this.stateMachine.transition(to)) return
    this.previousActivity = this.currentActivity
    this.activityEnteredAt = performance.now()
    this.activityBlend = 0
    this.speechPerformance.setSpeaking(activity === 'speaking')
    // Emit telemetry event
    eventBus.emit('character:runtime-telemetry', { type: 'state.transition', metadata: { from, to } })
    // Emit activity change so the React Store mirrors StateMachine state
    eventBus.emit('character:activity', { activity })
    switch (activity) {
      case 'idle':
        this.idleCtrl.setBreathing(true)
        this.exprCtrl.apply('neutral', 1, 520)
        if (this.motionArbiter.isPlaying()) {
          this.motionArbiter.enqueue('return_idle')
        }
        // Don't start native idle here — the update loop guard will do it
        // once the return_idle motion completes.
        // Pipeline idle does not cancel a presentation motion already in flight.
        break
      case 'thinking':
        this.idleCtrl.setBreathing(true)
        this.motionArbiter.play('thinking', 'system', 0.3)
        break
      case 'speaking':
        this.idleCtrl.setBreathing(true)
        if (
          !this.motionArbiter.isPlaying()
          || this.motionArbiter.currentMotion?.toLowerCase() === 'native:idle'
        ) this.motionArbiter.play('speak', 'system', 0.32)
        break
      case 'listening':
        this.idleCtrl.setBreathing(true)
        this.motionArbiter.stop()
        break
    }
  }

  /** Execute a semantic presentation plan through existing expression/motion controllers. */
  private applyIntent(intent: import('./CharacterBehaviorResolver').CharacterIntent): void {
    this._currentEmotion = intent.emotion || 'neutral'
    this._currentEmotionIntensity = Math.max(0, Math.min(1, intent.intensity ?? 1))
    this.vad.setEmotion(intent.emotion, intent.intensity ?? 1)
    eventBus.emit('character:runtime-telemetry', { type: 'intent.received', metadata: { emotion: intent.emotion, behavior: intent.behavior } })
    if (intent.naturalVAD) {
      this.vad.setTarget(intent.naturalVAD, Math.max(0.6, (intent.durationMs ?? 2400) / 1000))
    }
    const basePlan = this.behaviorResolver.resolve(intent)
    const policy = this.performancePolicy.evaluate(intent, basePlan, this.behaviorResolver.getConfig(), this._profile)
    this.exprCtrl.apply(policy.expression, policy.expressionIntensity, policy.transitionMs)
    if (policy.motion && Math.random() <= policy.motionProbability) {
      console.log('[MOTION APPLIED]', policy.motion, 'intensity:', policy.motionIntensity)
      this.motionArbiter.play(policy.motion, 'ai', policy.motionIntensity)
    }
    eventBus.emit('character:performance', {
      emotion: intent.emotion || 'neutral', behavior: intent.behavior || '', expression: policy.expression,
      motion: policy.motion || '', profile: this._profile?.model || this._modelName,
      transitionMs: policy.transitionMs, holdMs: policy.holdMs, motionProbability: policy.motionProbability,
      modifiers: { ...policy.modifiers },
    })
    if (this._performanceResetTimer) clearTimeout(this._performanceResetTimer)
    if (policy.holdMs > 0 && intent.activity !== 'speaking') {
      this._performanceResetTimer = setTimeout(() => {
        if (this.currentActivity === 'idle') {
          this.exprCtrl.apply('neutral', 1, Math.max(420, policy.transitionMs))
          this._currentEmotion = 'neutral'
          this._currentEmotionIntensity = 0
        }
      }, policy.holdMs)
    }
  }

  private applyOutputGains(): void {
    const modeGain = this._performanceMode === 'legacy' ? 1
      : this._performanceMode === 'calibration' ? 1.35 : 1
    this.parameterResolver.setOutputGains(
      this._performanceMode === 'legacy' ? 1 : this._parameterGain * modeGain,
      this._performanceMode === 'legacy' ? 1 : this._bodyMotionGain,
    )
  }

  private emitNativeCatalog(): void {
    eventBus.emit('character:native_catalog', {
      motions: this._nativeMotions,
      expressions: this._nativeExpressions,
    })
  }

  private startNativeIdleIfAvailable(): void {
    if (this.currentActivity !== 'idle' || this.motionArbiter.isPlaying()) return
    this.motionArbiter.play('idle', 'system', 0.7)
  }

  private submitLogicalLayer(
    source: string,
    values: Record<string, number>,
    priority: number,
  ): void {
    for (const [parameterId, value] of Object.entries(this.parameterResolver.values(values))) {
      this.mixer.submit({
        id: `${source}:${parameterId}`,
        parameterId,
        source,
        channel: parameterId.toLowerCase().includes('body') ? 'body' : 'head',
        value,
        mode: 'add',
        priority,
        createdAt: performance.now(),
      })
    }
  }

  detach(): void {
    this.cleanupFns.forEach((fn) => fn())
    this.cleanupFns = []
    this.paramCtrl.detach()
    this.idleCtrl.detach()
    if (this._performanceResetTimer) clearTimeout(this._performanceResetTimer)
    this.adapter = null
  }

  // ── Accessory control ──

  setAccessoryParts(parts: Record<string, string>): void {
    this._accessoryParts = parts
    this._accessoryState = {}
    for (const label of Object.keys(parts)) {
      this._accessoryState[label] = true
    }
  }

  clearAccessories(): void {
    this._accessoryParts = {}
    this._accessoryState = {}
    this._onAccessoryChange = null
  }

  setAccessoryEnabled(label: string, enabled: boolean): boolean {
    const exprName = this._accessoryParts[label]
    if (!exprName || !this.adapter) {
      console.warn('[Accessory] setAccessoryEnabled failed: label=%s exprName=%s', label, exprName)
      return false
    }
    this._accessoryState[label] = enabled

    // Submit accessory parameter contributions to mixer instead of direct write
    const preset = getExpression(exprName)
    if (preset) {
      for (const p of preset.params) {
        this.mixer.submit({
          id: `accessory:${label}:${p.id}`,
          parameterId: p.id,
          source: `accessory:${label}`,
          channel: 'accessory',
          value: enabled ? p.value : 0,
          mode: 'add',
          priority: 60,
          createdAt: performance.now(),
          persistent: true,
        })
      }
    }
    this._onAccessoryChange?.(label, enabled)
    return true
  }

  toggleAccessory(label: string): boolean {
    const current = this._accessoryState[label] ?? true
    return this.setAccessoryEnabled(label, !current)
  }

  getAccessoryState(): Record<string, boolean> { return { ...this._accessoryState } }
  getAccessoryParts(): Record<string, string> { return { ...this._accessoryParts } }

  onAccessoryChange(cb: (label: string, enabled: boolean) => void): void {
    this._onAccessoryChange = cb
  }

  resetAccessories(): void {
    for (const [label, enabled] of Object.entries(this._accessoryState)) {
      this.setAccessoryEnabled(label, enabled)
    }
  }

  // ── Mouse tracking ──

  setMouseTracking(enabled: boolean): void { this.headTrackingEnabled = enabled }

  resetMousePosition(): void {
    this.targetMouseX = 0
    this.targetMouseY = 0
    this.mouseX = 0
    this.mouseY = 0
  }

  setMousePos(x: number, y: number): void {
    this.targetMouseX = x
    this.targetMouseY = y
  }

  // ── Per-frame update ──

  /**
   * Main per-frame update. SUBMITS contributions to the mixer.
   * The caller (animation loop) is responsible for:
   *   mixer.resolve()
   *   mixer.apply(adapter)
   *   adapter.applyPose()
   *   adapter.updateModel()
   *   render(handle)
   */
  update(dt: number): void {
    if (!this.adapter) return

    // Step 1: Reset mixer frame
    this.mixer.resetFrame()

    const vadSnapshot = this.vad.update(dt)
    this.idleBehavior.setVAD(vadSnapshot.current)
    this.idleBehavior.update(dt, this.currentActivity === 'idle' && !this.motionArbiter.isPlaying())
    const idleSnapshot = this.idleBehavior.getSnapshot()
    const idleMotionScale = this._performanceMode === 'calibration' ? 1.45 : 1
    if (this._performanceMode !== 'legacy') {
      const calibrationGain = this._performanceMode === 'calibration' ? 1.8 : 1
      this.submitLogicalLayer(
        'vad_micro',
        this.vadMicroMotion.update(dt, vadSnapshot.current, this._style.microMotionGain * calibrationGain),
        13,
      )
      this.submitLogicalLayer(
        'vad_gesture',
        this.vadGesture.update(
          dt,
          vadSnapshot.current,
          this._style.gestureFrequency * calibrationGain,
          calibrationGain,
        ),
        26,
      )
      this.submitLogicalLayer(
        'voice_waiting',
        this.voiceWaiting.update(dt, this.currentActivity, calibrationGain),
        24,
      )
    }
    const privateParams = this.privateEmotion.update(
      this._performanceMode === 'legacy' ? 'neutral' : this._currentEmotion,
      this._performanceMode === 'legacy' ? 0 : this._currentEmotionIntensity,
      this._performanceMode === 'legacy'
        ? { valence: 0, arousal: 0, dominance: 0 }
        : vadSnapshot.current,
      this._profile?.privateEmotionMap,
    )
    for (const [parameterId, value] of Object.entries(privateParams)) {
      if (!this.adapter.hasParameter(parameterId)) continue
      this.mixer.submit({
        id: `private_emotion:${parameterId}`,
        parameterId,
        source: 'private_emotion',
        channel: 'expression',
        value,
        mode: 'add',
        priority: 42,
        createdAt: performance.now(),
      })
    }
    this.activityBlend = Math.min(1, (performance.now() - this.activityEnteredAt) / 420)
    const speechTarget = this.currentActivity === 'speaking' ? 1 : 0
    this.speechWeight += (speechTarget - this.speechWeight) * (1 - Math.exp(-dt * 7))
    const idleLayerWeight = 1 - this.speechWeight

    // Step 2: Expression interpolation contributions
    const exprContribs = this.paramCtrl.update()
    for (const c of exprContribs) {
      this.mixer.submit({
        id: `expr:${c.parameterId}`,
        parameterId: c.parameterId,
        source: c.source,
        channel: 'expression',
        value: c.value,
        priority: c.priority,
        createdAt: performance.now(),
      })
    }

    // Step 3: Idle animations
    this.idleCtrl.update(dt)

    // Step 4: Submit per-frame behaviors to mixer

    // 4a: Blink (priority 40)
    this.mixer.setParams('blink', this.idleCtrl.getBlinkParams(idleSnapshot.eyeClose * idleMotionScale))

    // 4b: Breath (priority 20)
    this.mixer.setParams('breath', this.idleCtrl.getBreathParams())

    const vadFacs = facsFromVAD(vadSnapshot.current)
    const vadPosture = this.parameterResolver.values({
      'eye.y': vadFacs.gazeY ?? 0,
      'head.y': vadFacs.headY ?? 0,
      'head.z': vadFacs.headZ ?? 0,
      'body.x': vadFacs.bodyX ?? 0,
      'body.y': vadFacs.bodyY ?? 0,
    })
    for (const [parameterId, value] of Object.entries(vadPosture)) {
      this.mixer.submit({
        id: `vad:${parameterId}`,
        parameterId,
        source: 'vad_posture',
        channel: parameterId.includes('Body') ? 'body' : 'head',
        value,
        mode: 'add',
        priority: 12,
        createdAt: performance.now(),
      })
    }

    // 4c: Lip-sync (priority 60)
    if (this.speechWeight > 0.01) {
      this.mixer.setParams('lip_sync', this.parameterResolver.values({ 'mouth.open': this._mouthOpenValue * this.speechWeight }))
    }

    const speechSample = this.speechPerformance.update(dt, this._mouthOpenValue)
    if (speechSample.weight > 0.01 || speechSample.state === 'releasing') {
      this.mixer.setParams('speech', this.parameterResolver.values({
        'head.x': speechSample.headX,
        'head.y': speechSample.headY,
        'head.z': speechSample.headZ,
        'body.x': speechSample.bodyX,
        'body.y': speechSample.bodyY,
      }), 45)
    }

    // 4d: Gaze tracking (priority 30) or idle head sway (priority 10)
    if (this.headTrackingEnabled && !this.motionArbiter.isPlaying()) {
      this.idleTime = 0
      const eyeSmooth = 0.18
      this.mouseX += (this.targetMouseX - this.mouseX) * eyeSmooth
      this.mouseY += (this.targetMouseY - this.mouseY) * eyeSmooth

      const cfg = getModelParamConfig(this._modelName)
      const headSmooth = 0.06
      this.headX += (this.targetMouseX - this.headX) * headSmooth
      this.headY += (this.targetMouseY - this.headY) * headSmooth
      const hx = this.headX
      const hy = this.headY
      const breathBX = this.idleCtrl.getBreathBodyX()
      const breathBY = this.idleCtrl.getBreathBodyY()

      if (PER_FRAME_GAZE_LOGGING) {
        console.debug(
          '[Gaze] mouse=(%+.3f,%+.3f) eye=(%+.3f,%+.3f) angle=(%+.3f,%+.3f,%+.3f)',
          this.mouseX, this.mouseY,
          this.mouseX * 0.85, cfg.eyeBallYSign * this.mouseY * 0.7,
          cfg.angleXSign * hx * 15, cfg.angleYSign * hy * 10, hx * 4,
        )
      }

      this.mixer.setParams('gaze', this.parameterResolver.values({
        'eye.x': this.mouseX * 0.85 + idleSnapshot.eyeX * idleMotionScale * idleLayerWeight,
        'eye.y': cfg.eyeBallYSign * this.mouseY * 0.7 + idleSnapshot.eyeY * idleMotionScale * idleLayerWeight,
        'head.x': cfg.angleXSign * hx * 15 + idleSnapshot.headX * idleMotionScale * idleLayerWeight,
        'head.y': cfg.angleYSign * hy * 10 + idleSnapshot.headY * idleMotionScale * idleLayerWeight,
        'head.z': hx * 4 + idleSnapshot.headZ * idleMotionScale * idleLayerWeight,
        'body.x': breathBX + idleSnapshot.bodyX * idleMotionScale * idleLayerWeight + hx * 4,
        'body.y': breathBY + idleSnapshot.bodyY * idleMotionScale * idleLayerWeight + hy * 3,
      }))
    } else {
      this.idleTime += dt
      this.mixer.setParams('idle_sway', this.parameterResolver.values({
        'head.x': idleSnapshot.headX * idleMotionScale * idleLayerWeight,
        'head.y': idleSnapshot.headY * idleMotionScale * idleLayerWeight,
        'head.z': idleSnapshot.headZ * idleMotionScale * idleLayerWeight,
        'eye.x': idleSnapshot.eyeX * idleMotionScale * idleLayerWeight,
        'eye.y': idleSnapshot.eyeY * idleMotionScale * idleLayerWeight,
        'body.x': idleSnapshot.bodyX * idleMotionScale * idleLayerWeight,
        'body.y': idleSnapshot.bodyY * idleMotionScale * idleLayerWeight,
      }))
    }

    // Step 5: Motion contributions
    for (const step of this.motionArbiter.drainDueSteps()) {
      if (step.type === 'expression') this.exprCtrl.apply(step.value, 1, 220)
      else if (step.type === 'motion') this.motionArbiter.enqueue(step.value)
      else if (step.type === 'attention') this.setMouseTracking(step.value !== 'away')
      else if (step.type === 'behavior') this.applyIntent({ emotion: 'neutral', behavior: step.value, intensity: 0.5 })
    }
    const motionContribs = this.motionArbiter.update(dt)
    const resolvedMotion = this.parameterResolver.resolveMotionParameters(
      Object.fromEntries(motionContribs.map(c => [c.logicalParameter, c.value])),
    )
    for (const [parameterId, value] of Object.entries(resolvedMotion)) {
      this.mixer.submit({
        id: `motion:${parameterId}`,
        parameterId,
        source: `motion:${this.motionArbiter.currentMotion ?? 'unknown'}`,
        channel: 'motion',
        value,
        priority: 50,
        createdAt: performance.now(),
      })
    }
    for (const contribution of this.motionArbiter.drainNativeContributions()) {
      this.mixer.submit({
        id: `native-motion:${contribution.parameterId}`,
        parameterId: contribution.parameterId,
        source: `native-motion:${this.motionArbiter.currentMotion ?? 'unknown'}`,
        channel: 'motion',
        value: contribution.value,
        weight: contribution.weight,
        priority: 50,
        createdAt: performance.now(),
      })
    }
    // Detect motion arbiter transition: playing → idle (for idle restart guard below)
    if (this._wasPlaying && !this.motionArbiter.isPlaying()) {
      this._lastMotionEnded = true
    }
    this._wasPlaying = this.motionArbiter.isPlaying()

    // Resume authored idle only once after motion completes, not every idle frame.
    if (this.currentActivity === 'idle' && !this.motionArbiter.isPlaying() && this._lastMotionEnded) {
      this._lastMotionEnded = false
      this.startNativeIdleIfAvailable()
    }
    // Fallback: if idle with no motion and no native idle started yet, start it.
    if (this.currentActivity === 'idle' && !this.motionArbiter.isPlaying()
        && !this.motionArbiter.currentMotion && !this._lastMotionEnded) {
      this.startNativeIdleIfAvailable()
    }
    if (
      this.currentActivity !== 'speaking'
      && this.motionArbiter.currentMotion?.toLowerCase() === 'native:idle'
      && (this._profile?.idleMouthOpen ?? 0) > 0
    ) {
      const idleMouth = this.parameterResolver.values({
        'mouth.open': this._profile!.idleMouthOpen!,
      })
      for (const [parameterId, value] of Object.entries(idleMouth)) {
        this.mixer.submit({
          id: `idle_mouth_baseline:${parameterId}`,
          parameterId,
          source: 'idle_mouth_baseline',
          channel: 'lip_sync',
          value,
          mode: 'add',
          priority: 18,
          createdAt: performance.now(),
        })
      }
    }

    const now = performance.now()
    if (now - this.lastDebugEmitAt >= 250) {
      this.lastDebugEmitAt = now
      const mixerFrame = this.mixer.debugFrame()
      const contestedParameters = Object.fromEntries(
        Object.entries(mixerFrame.frameValues).filter(([, values]) => values.length > 1),
      )
      const bindings = Object.entries(this.parameterResolver.getBindings())
      const missingBindings = bindings
        .filter(([, target]) => !this.adapter!.hasParameter(target))
        .map(([logical, target]) => ({ logical, target }))
      const resolvedCount = bindings.length - missingBindings.length
      eventBus.emit('character:performance_debug', {
        activity: this.currentActivity,
        previousActivity: this.previousActivity,
        transitionProgress: this.activityBlend,
        vad: this.vad.getSnapshot(),
        expression: {
          name: this.exprCtrl.getCurrent(),
          intensity: this.exprCtrl.getIntensity(),
        },
        motion: this.motionArbiter.getDebugState(),
        idle: { ...this.idleBehavior.getSnapshot() },
        lipSync: { ...this.audioAnalyzer.getDebugInfo() },
        pose: this.adapter.getPoseDebug(),
        profileCoverage: {
          bindingCount: bindings.length,
          resolvedCount,
          coverage: bindings.length ? resolvedCount / bindings.length : 1,
          missingBindings,
        },
        performanceTuning: {
          mode: this._performanceMode,
          parameterGain: this._parameterGain,
          bodyMotionGain: this._bodyMotionGain,
        },
        contestedParameters,
      })
    }
  }

  getLipSyncDebug() {
    return this.audioAnalyzer.getDebugInfo()
  }

  getMixerDebug(): string {
    const info = this.mixer.debugFrame()
    return Object.entries(info.resolved)
      .map(([k, v]) => `${k}=${v.toFixed(3)}`)
      .join('  ')
  }
}
const PER_FRAME_GAZE_LOGGING = isPerFrameGazeLoggingEnabled(
  (globalThis as {
    __SOULLINK_DIAGNOSTICS__?: { gazeFrames?: boolean }
  }).__SOULLINK_DIAGNOSTICS__?.gazeFrames,
)
