// Frontend Component Manager — manages avatar component (accessory) visibility.
//
// Components are controlled via expression presets (param values with "Add" blend)
// and PartOpacity (drawable visibility).
//
// ComponentManager does NOT hold CubismModelHandle. All parameter writes are
// submitted to ParameterMixer → Live2DModelAdapter.

import type { ParameterMixer } from './ParameterMixer'

export interface ComponentInfo {
  name: string
  displayName: string
  expression: string
  paramIds: string[]
  partIds: string[]
  category: string
}

export class ComponentManager {
  private _mixer: ParameterMixer | null = null
  private _state: Record<string, boolean> = {}
  private _componentInfo: Record<string, ComponentInfo> = {}

  /** Attach a ParameterMixer reference for submitting contributions. */
  attach(mixer: ParameterMixer): void {
    this._mixer = mixer
  }

  detach(): void {
    this._mixer = null
  }

  registerComponents(components: Record<string, any>): void {
    for (const [key, cfg] of Object.entries(components)) {
      const c = cfg as Record<string, any>
      this._componentInfo[key] = {
        name: key,
        displayName: c.display_name || key,
        expression: c.expression || '',
        paramIds: c.param_ids || [],
        partIds: c.part_ids || [],
        category: c.category || 'accessory',
      }
    }
  }

  /** Enable or disable a component by config key. */
  setEnabled(name: string, enabled: boolean): void {
    this._state[name] = enabled
    const info = this._componentInfo[name]
    if (!info) {
      console.warn('[ComponentManager] Unknown component: %s', name)
      return
    }

    // Expression-backed components are submitted by CharacterController.
    // Replaying the same preset here created two persistent owners for every
    // toggle. ComponentManager only handles explicit param_ids below.

    // Method 2: Direct parameter control
    for (const paramId of info.paramIds) {
      this._submitParameter(paramId, enabled ? 1 : 0, `comp:${name}:param`)
    }
  }

  /** Submit a parameter contribution to the mixer. */
  private _submitParameter(parameterId: string, value: number, source: string): void {
    if (!this._mixer) {
      console.warn('[ComponentManager] No mixer, deferring: %s=%s', parameterId, value)
      return
    }
    this._mixer.submit({
      id: `${source}:${parameterId}`,
      parameterId,
      source,
      channel: 'accessory',
      value,
      mode: 'add',
      priority: 60,
      createdAt: performance.now(),
      persistent: true,
    })
  }

  toggle(name: string): boolean {
    const current = this._state[name] ?? false
    this.setEnabled(name, !current)
    return !current
  }

  isEnabled(name: string): boolean { return this._state[name] ?? false }
  getAllStates(): Record<string, boolean> { return { ...this._state } }
  getInfo(name: string): ComponentInfo | undefined { return this._componentInfo[name] }

  applyAllStates(state: Record<string, boolean>): void {
    for (const [name, enabled] of Object.entries(state)) {
      this.setEnabled(name, enabled)
    }
  }

  resetAll(info: Record<string, any>): void {
    for (const [key, cfg] of Object.entries(info)) {
      const c = cfg as Record<string, any>
      this.setEnabled(key, c.default_state ?? false)
    }
  }
}
