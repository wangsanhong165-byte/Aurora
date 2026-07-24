// Pet Mode Controller — state machine for desktop pet UX.
//
// States:
//   OFF      Pet mode disabled (normal window)
//   IDLE     Character idle with autonomous behaviors
//   INTERACT User clicked the character — plays response animation
//   SPEAKING Character is talking — suppresses idle
//
// Transitions driven by: store.windowMode, click events, character_state events.

import { eventBus } from '../core/event-bus'

export type PetState = 'OFF' | 'IDLE' | 'INTERACT' | 'SPEAKING'

const IDLE_INTERVAL_MIN = 8000   // 8 seconds
const IDLE_INTERVAL_MAX = 18000  // 18 seconds
const INTERACT_COOLDOWN = 1800
const INTERACT_TIMEOUT = 4000    // 4 seconds → return to IDLE

export class PetModeController {
  private _state: PetState = 'OFF'
  private _idleTimer: ReturnType<typeof setTimeout> | null = null
  private _interactTimer: ReturnType<typeof setTimeout> | null = null
  private _lastInteractionAt = 0
  /** Unique instance ID — used by CharacterView to detect duplicate instances. */
  public readonly instanceId: number
  private static _nextId = 1

  constructor() {
    this.instanceId = PetModeController._nextId++
  }

  get state(): PetState { return this._state }

  /** Enable pet mode. Called when store.windowMode changes to 'pet'. */
  enable(): void {
    if (this._state !== 'OFF') return
    this._state = 'IDLE'
    console.log('[PET] Mode ON → IDLE')
    this._scheduleIdle()
  }

  /** Disable pet mode. Called when store.windowMode changes to 'window'. */
  disable(): void {
    this._clearTimers()
    this._state = 'OFF'
    console.log('[PET] Mode OFF')
  }

  /** User clicked the character in pet mode. */
  onInteraction(): void {
    if (this._state === 'OFF' || this._state === 'SPEAKING' || this._state === 'INTERACT') return
    const now = performance.now()
    if (now - this._lastInteractionAt < INTERACT_COOLDOWN) return
    this._lastInteractionAt = now

    this._state = 'INTERACT'
    this._clearTimers()

    // Pick a friendly response expression
    console.log('[PET] INTERACT -> gentle acknowledgement')
    eventBus.emit('character:intent', {
      emotion: 'happy',
      behavior: 'agree',
      intensity: 0.38,
    })

    // Return to idle after timeout
    this._interactTimer = setTimeout(() => {
      if (this._state === 'INTERACT') {
        this._state = 'IDLE'
        console.log('[PET] INTERACT → IDLE (timeout)')
        this._scheduleIdle()
      }
    }, INTERACT_TIMEOUT)
  }

  /** Runtime reports character is speaking. */
  onSpeakingStart(): void {
    if (this._state === 'OFF') return
    const prev = this._state
    this._state = 'SPEAKING'
    this._clearTimers()
    console.log('[PET] %s → SPEAKING', prev)
  }

  /** Runtime reports character is idle. */
  onSpeakingEnd(): void {
    if (this._state === 'OFF') return
    console.log('[PET] SPEAKING → IDLE')
    this._state = 'IDLE'
    // Delay before resuming autonomous idle (give user time to read)
    setTimeout(() => {
      if (this._state === 'IDLE') {
        this._scheduleIdle()
      }
    }, 5000)
  }

  private _scheduleIdle(): void {
    this._clearIdleTimer()
    const delay = IDLE_INTERVAL_MIN + Math.random() * (IDLE_INTERVAL_MAX - IDLE_INTERVAL_MIN)
    this._idleTimer = setTimeout(() => {
      if (this._state === 'IDLE') {
        eventBus.emit('character:interaction', { type: 'inactivity', intensity: 0.22 })
        // Continuous autonomous performance is owned by IdleBehaviorController.
        this._scheduleIdle()
      }
    }, delay)
  }

  private _clearIdleTimer(): void {
    if (this._idleTimer) { clearTimeout(this._idleTimer); this._idleTimer = null }
  }

  private _clearInteractTimer(): void {
    if (this._interactTimer) { clearTimeout(this._interactTimer); this._interactTimer = null }
  }

  private _clearTimers(): void {
    this._clearIdleTimer()
    this._clearInteractTimer()
  }
}
