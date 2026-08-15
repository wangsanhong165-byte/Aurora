// Frontend Avatar Controller — receives avatar protocol messages and coordinates
// component, expression, and motion subsystems through the permission system.
//
// Architecture: User UI / AI Brain → AvatarController (Python) → Avatar Protocol (WS)
//               → client.ts dispatch → eventBus → AvatarController (this, TS)
//               → CharacterController / ComponentManager → CubismModelHandle parameters

import { eventBus } from '../core/event-bus'
import type { CharacterController } from './controllers'
import type { ComponentManager } from './ComponentManager'

export interface AvatarState {
  components: Record<string, boolean>
  expression: string
  expressionPreset: string
  expressionIntensity: number
  motion: string
  motionLoop: boolean
}

/**
 * Receives avatar protocol messages from the server and dispatches them
 * to the appropriate frontend controllers. Subscribes to eventBus avatar
 * events (emitted by client.ts) and drives CharacterController /
 * ComponentManager actions.
 */
export class AvatarController {
  private _state: AvatarState = {
    components: {},
    expression: 'neutral',
    expressionPreset: 'neutral',
    expressionIntensity: 1.0,
    motion: 'idle',
    motionLoop: true,
  }

  private _ctrl: CharacterController | null = null
  private _compMgr: ComponentManager | null = null
  private _cleanupFns: (() => void)[] = []

  /** Wire up to CharacterController and ComponentManager for model control. */
  wire(ctrl: CharacterController, compMgr: ComponentManager): void {
    this._ctrl = ctrl
    this._compMgr = compMgr
  }

  /** Start listening for avatar messages from the event bus. */
  attach(): void {
    this.detach()

    this._cleanupFns.push(
      eventBus.on('avatar:component_update', (data) => {
        this._state.components[data.displayName || data.name] = data.enabled
        // Forward to ComponentManager for actual model parameter control
        if (this._compMgr) {
          this._compMgr.setEnabled(data.name, data.enabled)
        }
        // Also emit legacy accessory event for backward compat (SettingsPanel UI)
        eventBus.emit('accessory:set', {
          label: data.displayName || data.name,
          enabled: data.enabled,
        })
      }),
    )

    this._cleanupFns.push(
      eventBus.on('avatar:expression_update', (data) => {
        this._state.expression = data.name
        this._state.expressionPreset = data.name
        this._state.expressionIntensity = data.intensity
        // Forward to CharacterController for expression application
        if (this._ctrl) {
          this._ctrl.exprCtrl.apply(data.name, data.intensity, 500)
        }
      }),
    )

    this._cleanupFns.push(
      eventBus.on('avatar:motion_update', (data) => {
        this._state.motion = data.name
        this._state.motionLoop = data.loop
        // Forward to CharacterController
        if (this._ctrl && !data.loop) {
          this._ctrl.motionArbiter.play(data.name)
        }
      }),
    )

    this._cleanupFns.push(
      eventBus.on('avatar:state_restored', (data) => {
        this._state.components = data.components
        this._state.expression = data.expression
        this._state.expressionIntensity = data.intensity
        this._state.motion = data.motion

        // Restore expression
        if (data.expression !== 'neutral' && this._ctrl) {
          this._ctrl.exprCtrl.apply(data.expression, data.intensity, 0)
        }

        // Restore components
        if (this._compMgr) {
          this._compMgr.applyAllStates(data.components)
        }

        // Emit individual component states for UI
        for (const [name, enabled] of Object.entries(data.components)) {
          eventBus.emit('accessory:set', { label: name, enabled })
        }
      }),
    )

    this._cleanupFns.push(
      eventBus.on('avatar:suggestion', (data) => {
        // Forward to UI layer for user decision dialog
        eventBus.emit('avatar:suggestion', data)
      }),
    )
  }

  /** Stop listening. */
  detach(): void {
    this._cleanupFns.forEach(fn => fn())
    this._cleanupFns = []
  }

  /** Send a user control command to the server. */
  sendRequest(target: string, name: string, action: string): void {
    eventBus.emit('avatar:send', {
      eventType: 'character.control.requested',
      payload: {
        action,
        requestId: `request_${crypto.randomUUID()}`,
        params: { target, name, source: 'user', priority: 100 },
      },
    })
  }

  /** Accept an AI suggestion. */
  acceptSuggestion(suggestionId: string): void {
    eventBus.emit('avatar:send', {
      eventType: 'character.suggestion.accepted',
      payload: { suggestionId },
    })
  }

  /** Reject an AI suggestion. */
  rejectSuggestion(suggestionId: string): void {
    eventBus.emit('avatar:send', {
      eventType: 'character.suggestion.rejected',
      payload: { suggestionId, reason: 'user' },
    })
  }

  /** Get current avatar state. */
  getState(): AvatarState {
    return { ...this._state }
  }
}
