// Parameter Mixer — resolves conflicts when multiple subsystems write to the
// same Cubism parameter. This is the SINGLE arbitration point for all
// real-time parameter contributions.
//
// Flow:
//   1. Each subsystem submits ParameterContribution objects via submit() or setParams()
//   2. At resolve(), the mixer arbitrates per-parameter conflicts
//   3. apply() writes final values to the Live2DModelAdapter
//
// Priority conventions:
//   system safety/reset:  100
//   ui/debug override:     90
//   ai motion:             80
//   ai expression:         75
//   motion playback:       50
//   lip_sync:              60
//   pet interaction:       60
//   gaze:                  30
//   blink:                 40  (absolute override when eyes closing)
//   breath:                20
//   idle_sway:             10
//
// Channels:
//   motion, expression, lip_sync, eye, head, body, blink, breath, accessory, pose

import type { Live2DModelAdapter } from './Live2DModelAdapter'

export type ControlSource =
  | 'system'
  | 'runtime'
  | 'ai'
  | 'speech'
  | 'mouse'
  | 'idle'
  | 'pet'
  | 'ui'
  | 'debug'

export type ControlChannel =
  | 'expression'
  | 'lip_sync'
  | 'eye'
  | 'head'
  | 'body'
  | 'blink'
  | 'breath'
  | 'accessory'
  | 'pose'
  | 'calibration'
  | 'motion'

export interface ParameterContribution {
  /** Unique contribution ID for deduplication. */
  id: string
  /** Cubism parameter ID, e.g. "ParamAngleX". */
  parameterId: string
  /** Source identifier for debugging. */
  source: string
  /** Control channel for arbitration grouping. */
  channel: ControlChannel
  /** Parameter value. */
  value: number
  /** How this contribution combines with the resolved base value. */
  mode?: 'override' | 'add' | 'multiply'
  /** Priority (higher = wins conflicts). */
  priority: number
  /** Optional weight for blended contributions. */
  weight?: number
  /** Timestamp when this contribution was created. */
  createdAt: number
  /** Optional expiry — contribution is removed after this time. */
  expiresAt?: number
  /** Preserve this contribution across frames until explicitly removed. */
  persistent?: boolean
}

export interface PartOpacityContribution {
  id: string
  partId: string
  opacity: number
  priority: number
  weight?: number
  persistent?: boolean
}

interface ParameterOwner {
  name: string
  paramIds: string[]
  priority: number
  maskWeight: number
}

interface ParameterValue {
  paramId: string
  value: number
  source: string
  priority: number
  weight: number
  mode: 'override' | 'add' | 'multiply'
}

interface MixerDebugFrame {
  frameValues: Record<string, Array<{ source: string; value: number; priority: number }>>
  resolved: Record<string, number>
}

export class ParameterMixer {
  private _owners: Map<string, ParameterOwner> = new Map()
  private _frameValues: Map<string, ParameterValue[]> = new Map()
  private _resolved: Record<string, number> = {}
  // Persistent contributions (not cleared per-frame, e.g. accessories)
  private _persistentContributions: Map<string, ParameterContribution> = new Map()
  private _persistentPartOpacityContributions: Map<string, PartOpacityContribution> = new Map()
  private _partOpacityFrame: Map<string, PartOpacityContribution[]> = new Map()
  private _resolvedPartOpacities: Record<string, number> = {}
  private _baselineProvider: ((parameterId: string) => number) | null = null
  private _baselines = new Map<string, number>()

  setBaselineProvider(provider: ((parameterId: string) => number) | null): void {
    this._baselineProvider = provider
    this._baselines.clear()
  }

  private _baseline(parameterId: string): number {
    if (!this._baselines.has(parameterId)) {
      this._baselines.set(parameterId, this._baselineProvider?.(parameterId) ?? 0)
    }
    return this._baselines.get(parameterId)!
  }

  getBaseline(parameterId: string): number {
    return this._baseline(parameterId)
  }

  // ── Owner registration ─────────────────────────────────────

  registerOwner(name: string, paramIds: string[], priority: number, maskWeight = 1.0): void {
    this._owners.set(name, { name, paramIds, priority, maskWeight })
  }

  registerAll(config: Record<string, { owns: string[]; priority: number; mask_weight?: number }>): void {
    for (const [name, cfg] of Object.entries(config)) {
      this.registerOwner(name, cfg.owns, cfg.priority, cfg.mask_weight ?? 1.0)
    }
  }

  getOwner(name: string): ParameterOwner | undefined {
    return this._owners.get(name)
  }

  // ── Contribution API (NEW — preferred for all new code) ─────

  /**
   * Submit a parameter contribution for the current frame.
   * Contributions with the same id (for persistent ones) will be updated.
   */
  submit(contribution: ParameterContribution): void {
    // Only explicit persistent values or TTL values survive resetFrame().
    if (contribution.persistent || contribution.expiresAt) {
      this._persistentContributions.set(contribution.id, contribution)
    }
    this._addToFrame(contribution)
  }

  private _addToFrame(contribution: ParameterContribution): void {
    if (!this._frameValues.has(contribution.parameterId)) {
      this._frameValues.set(contribution.parameterId, [])
    }
    this._frameValues.get(contribution.parameterId)!.push({
      paramId: contribution.parameterId,
      value: contribution.value,
      source: contribution.source,
      priority: contribution.priority,
      weight: contribution.weight ?? 1.0,
      mode: contribution.mode ?? 'override',
    })
  }

  /**
   * Remove a persistent contribution by id.
   */
  removeContribution(id: string): void {
    this._persistentContributions.delete(id)
  }

  /** Queue a part opacity write so the adapter remains the only SDK writer. */
  submitPartOpacity(contribution: PartOpacityContribution): void {
    if (contribution.persistent) {
      this._persistentPartOpacityContributions.set(contribution.id, contribution)
    }
    this._addPartOpacityToFrame(contribution)
  }

  removePartOpacityContribution(id: string): void {
    this._persistentPartOpacityContributions.delete(id)
  }

  private _addPartOpacityToFrame(contribution: PartOpacityContribution): void {
    const values = this._partOpacityFrame.get(contribution.partId) ?? []
    const existingIndex = values.findIndex(value => value.id === contribution.id)
    if (existingIndex >= 0) values[existingIndex] = contribution
    else values.push(contribution)
    this._partOpacityFrame.set(contribution.partId, values)
  }

  // ── Legacy per-frame submission (for backward compat during migration) ──

  setParams(source: string, values: Record<string, number>, priority?: number): void {
    const owner = this._owners.get(source)
    const srcPriority = priority !== undefined ? priority : (owner?.priority ?? 10)
    const weight = owner?.maskWeight ?? 1.0

    for (const [paramId, value] of Object.entries(values)) {
      if (!this._frameValues.has(paramId)) {
        this._frameValues.set(paramId, [])
      }
      this._frameValues.get(paramId)!.push({
        paramId,
        value,
        source,
        priority: srcPriority,
        weight,
        mode: 'override',
      })
    }
  }

  resetFrame(now = performance.now()): void {
    this._frameValues.clear()
    this._partOpacityFrame.clear()
    for (const [id, contribution] of this._persistentContributions) {
      if (contribution.expiresAt !== undefined && contribution.expiresAt <= now) {
        this._persistentContributions.delete(id)
        continue
      }
      this._addToFrame(contribution)
    }
    for (const contribution of this._persistentPartOpacityContributions.values()) {
      this._addPartOpacityToFrame(contribution)
    }
  }

  // ── Resolution ──────────────────────────────────────────────

  /** Resolve all parameter conflicts. */
  resolve(): Record<string, number> {
    this._resolved = {}

    for (const [paramId, values] of this._frameValues.entries()) {
      this._resolved[paramId] = this._blend(paramId, values)
    }
    this.resolvePartOpacities()

    return { ...this._resolved }
  }

  resolvePartOpacities(): Record<string, number> {
    this._resolvedPartOpacities = {}
    for (const [partId, values] of this._partOpacityFrame) {
      const ordered = [...values].sort((a, b) => a.priority - b.priority)
      let resolved = 1
      for (const value of ordered) {
        const weight = Math.max(0, Math.min(1, value.weight ?? 1))
        const opacity = Math.max(0, Math.min(1, value.opacity))
        resolved += (opacity - resolved) * weight
      }
      this._resolvedPartOpacities[partId] = resolved
    }
    return { ...this._resolvedPartOpacities }
  }

  private _blend(paramId: string, values: ParameterValue[]): number {
    // Rule 1: Absolute blink override — when eyes are closing/closed, blink wins.
    const blinkValues = values.filter(v => v.source === 'blink')
    if (blinkValues.length > 0) {
      if (blinkValues.some(v => v.value < 0.5)) {
        return blinkValues[0].value
      }
    }

    // Exclusive arbitration for 'override' contributions: the highest-priority
    // override owns the parameter and fades from the model baseline by its own
    // weight. Lower-priority overrides never pre-load the value, so two
    // opposing poses cannot land the parameter in-between ("ghost arms").
    // 'add' and 'multiply' contributions accumulate on top of the resolved
    // override, matching the reference SDK's exclusive-group semantics.
    const overrides = values.filter(v => v.mode === 'override')
    const additions = values.filter(v => v.mode === 'add')
    const multipliers = values.filter(v => v.mode === 'multiply')

    let result = this._baseline(paramId)
    if (overrides.length > 0) {
      overrides.sort((a, b) => b.priority - a.priority || b.weight - a.weight)
      const winner = overrides[0]
      const weight = Math.max(0, Math.min(1, winner.weight))
      result += (winner.value - result) * weight
    }
    for (const contribution of additions) {
      result += contribution.value * Math.max(0, Math.min(1, contribution.weight))
    }
    for (const contribution of multipliers) {
      result *= 1 + (contribution.value - 1) * Math.max(0, Math.min(1, contribution.weight))
    }
    return result
  }

    /* Legacy unweighted arbitration retained only as migration reference.
    const overrides = values.filter(v => v.mode === 'override')
    const additions = values.filter(v => v.mode === 'add')
    const multipliers = values.filter(v => v.mode === 'multiply')

    // Rule 2: Highest priority wins for body/head/motion/arm parameters.
    //   Weighted average produces "ghost" positions (four arms) when two
    //   controllers write opposing override values — the arm appears in-between.
    if (overrides.length > 0) {
      overrides.sort((a, b) => b.priority - a.priority || b.weight - a.weight)
      let resolved = overrides[0].value
      for (const addition of additions) {
        resolved += addition.value * addition.weight
      }
      for (const multiplier of multipliers) {
        resolved *= multiplier.value
      }
      return resolved
    }

    // Pure additive/multiply: weighted average.
    let blended = 0
    let weightSum = 0
    for (const addition of additions) {
      const w = addition.priority * addition.weight
      blended += addition.value * w
      weightSum += w
    }
    let result = weightSum === 0 ? 0 : blended / weightSum
    for (const multiplier of multipliers) {
      result *= multiplier.value
    }
    return result
    */
  // ── Apply resolved values to adapter ─────────────────────────

  /** Apply resolved parameters to the Live2DModelAdapter (the ONLY write path). */
  apply(adapter: Live2DModelAdapter): void {
    for (const [paramId, value] of Object.entries(this._resolved)) {
      adapter.setParameter(paramId, value)
    }
    for (const [partId, opacity] of Object.entries(this._resolvedPartOpacities)) {
      adapter.setPartOpacity(partId, opacity)
    }
  }

  // ── Query ───────────────────────────────────────────────────

  getResolved(paramId: string): number | undefined {
    return this._resolved[paramId]
  }

  getAllResolved(): Record<string, number> {
    return { ...this._resolved }
  }

  getAllResolvedPartOpacities(): Record<string, number> {
    return { ...this._resolvedPartOpacities }
  }

  debugFrame(): MixerDebugFrame {
    const frameValues: Record<string, Array<{ source: string; value: number; priority: number }>> = {}
    for (const [pid, vals] of this._frameValues.entries()) {
      frameValues[pid] = vals.map(v => ({
        source: v.source,
        value: v.value,
        priority: v.priority,
      }))
    }
    return { frameValues, resolved: { ...this._resolved } }
  }
}
