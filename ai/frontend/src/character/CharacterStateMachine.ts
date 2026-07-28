// CharacterStateMachine — deterministic activity state transitions
// Single source of truth for idle/listening/thinking/speaking

export type CharacterActivity = 'idle' | 'listening' | 'thinking' | 'speaking'

export const VALID_TRANSITIONS: Record<CharacterActivity, CharacterActivity[]> = {
  idle: ['listening', 'thinking', 'speaking'],
  listening: ['thinking', 'speaking', 'idle'],
  thinking: ['speaking', 'idle'],
  speaking: ['idle'],
}

export class CharacterStateMachine {
  private _activity: CharacterActivity = 'idle'
  private _previousActivity: CharacterActivity = 'idle'
  private _enteredAt = 0
  private _listeners: Array<(from: CharacterActivity, to: CharacterActivity) => void> = []

  get activity(): CharacterActivity {
    return this._activity
  }

  get previousActivity(): CharacterActivity {
    return this._previousActivity
  }

  get elapsedMs(): number {
    return this._enteredAt ? performance.now() - this._enteredAt : 0
  }

  get isIdle(): boolean {
    return this._activity === 'idle'
  }

  get isSpeaking(): boolean {
    return this._activity === 'speaking'
  }

  transition(to: CharacterActivity): boolean {
    if (to === this._activity) return false
    const allowed = VALID_TRANSITIONS[this._activity]
    if (!allowed || !allowed.includes(to)) {
      console.warn(`[StateMachine] Invalid transition: ${this._activity} → ${to}`)
      return false
    }
    const from = this._activity
    this._previousActivity = this._activity
    this._activity = to
    this._enteredAt = performance.now()
    for (const listener of this._listeners) {
      try { listener(from, to) } catch {}
    }
    return true
  }

  /** Force a transition (used when the system is out of sync). */
  force(to: CharacterActivity): void {
    const from = this._activity
    this._previousActivity = this._activity
    this._activity = to
    this._enteredAt = performance.now()
    for (const listener of this._listeners) {
      try { listener(from, to) } catch {}
    }
  }

  onTransition(fn: (from: CharacterActivity, to: CharacterActivity) => void): () => void {
    this._listeners.push(fn)
    return () => {
      const idx = this._listeners.indexOf(fn)
      if (idx >= 0) this._listeners.splice(idx, 1)
    }
  }

  reset(): void {
    this._activity = 'idle'
    this._previousActivity = 'idle'
    this._enteredAt = performance.now()
  }
}
