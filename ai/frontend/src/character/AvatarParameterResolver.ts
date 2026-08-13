import type {
  AvatarCapabilityProfile,
  AvatarLipSyncConfig,
  AvatarParameterBinding,
} from './AvatarCapabilityProfile'

const DEFAULT_LIP_SYNC: Required<AvatarLipSyncConfig> = {
  min: 0,
  max: 0.82,
  inputGain: 6.5,
  noiseGate: 0.012,
  attackMs: 42,
  releaseMs: 145,
  peakBoost: 0.16,
}

const DEFAULT_PROTECTED_MOTION_PARAMETERS = new Set([
  'mouth.open',
])

/** Resolves logical performance keys to the current model's Cubism IDs. */
export class AvatarParameterResolver {
  private _profile: AvatarCapabilityProfile | undefined
  private parameterGain = 1
  private bodyMotionGain = 1

  setProfile(profile: AvatarCapabilityProfile | undefined): void { this._profile = profile }
  setOutputGains(parameterGain = 1, bodyMotionGain = 1): void {
    this.parameterGain = Math.max(0.4, Math.min(5, parameterGain))
    this.bodyMotionGain = Math.max(0, Math.min(4, bodyMotionGain))
  }
  resolve(logicalParameter: string): string | undefined {
    const binding = this._profile?.bindings[logicalParameter]
    return typeof binding === 'string' ? binding : binding?.target
  }
  getBindings(): Record<string, string> {
    return Object.fromEntries(
      Object.keys(this._profile?.bindings ?? {})
        .map(logical => [logical, this.resolve(logical)])
        .filter((entry): entry is [string, string] => Boolean(entry[1])),
    )
  }
  values(entries: Record<string, number>): Record<string, number> {
    const result: Record<string, number> = {}
    for (const [logical, value] of Object.entries(entries)) {
      if (!this.supportsLogicalParameter(logical)) continue
      const binding = this._profile?.bindings[logical]
      const id = typeof binding === 'string' ? binding : binding?.target
      if (id) {
        const expressive = logical.startsWith('head.')
          || logical.startsWith('eye.')
          || logical.startsWith('body.')
          || logical.startsWith('tail.')
          || logical === 'mouth.form'
        const gain = (expressive ? this.parameterGain : 1)
          * (logical.startsWith('body.') || logical.startsWith('tail.') ? this.bodyMotionGain : 1)
        result[id] = this.clampLogical(logical, this.applyBinding(value * gain, binding))
      }
    }
    return result
  }
  resolveMotionParameters(entries: Record<string, number>): Record<string, number> {
    const protectedParameters = this.protectedMotionParameters()
    return this.values(Object.fromEntries(
      Object.entries(entries).filter(([logical]) => !protectedParameters.has(logical)),
    ))
  }
  /** Resolve centered logical motion values as offsets for additive mixing. */
  resolveMotionDeltas(entries: Record<string, number>): Record<string, number> {
    const protectedParameters = this.protectedMotionParameters()
    const result: Record<string, number> = {}
    for (const [logical, value] of Object.entries(entries)) {
      if (protectedParameters.has(logical) || !this.supportsLogicalParameter(logical)) continue
      const binding = this._profile?.bindings[logical]
      const id = typeof binding === 'string' ? binding : binding?.target
      if (!id) continue
      const expressive = logical.startsWith('head.')
        || logical.startsWith('eye.')
        || logical.startsWith('body.')
        || logical.startsWith('tail.')
        || logical === 'mouth.form'
      const gain = (expressive ? this.parameterGain : 1)
        * (logical.startsWith('body.') || logical.startsWith('tail.') ? this.bodyMotionGain : 1)
      const scale = typeof binding === 'string' ? 1 : binding?.scale ?? 1
      const sign = typeof binding !== 'string' && binding?.mode === 'subtract' ? -1 : 1
      result[id] = this.clampLogical(logical, value * gain * scale * sign)
    }
    return result
  }

  isProtectedMotionTarget(parameterId: string): boolean {
    for (const logical of this.protectedMotionParameters()) {
      if (this.resolve(logical) === parameterId) return true
    }
    return false
  }

  getLipSyncConfig(): Required<AvatarLipSyncConfig> {
    const configured = this._profile?.lipSync ?? {}
    const min = Math.max(0, configured.min ?? DEFAULT_LIP_SYNC.min)
    const max = Math.max(min, Math.min(1, configured.max ?? DEFAULT_LIP_SYNC.max))
    return {
      min,
      max,
      inputGain: Math.max(0.1, configured.inputGain ?? DEFAULT_LIP_SYNC.inputGain),
      noiseGate: Math.max(0, configured.noiseGate ?? DEFAULT_LIP_SYNC.noiseGate),
      attackMs: Math.max(1, configured.attackMs ?? DEFAULT_LIP_SYNC.attackMs),
      releaseMs: Math.max(1, configured.releaseMs ?? DEFAULT_LIP_SYNC.releaseMs),
      peakBoost: Math.max(0, configured.peakBoost ?? DEFAULT_LIP_SYNC.peakBoost),
    }
  }

  supportsLogicalParameter(logical: string): boolean {
    const capabilities = this._profile?.capabilities
    if (!capabilities) return true
    if (logical.startsWith('head.')) return capabilities.headControl !== false
    if (logical.startsWith('body.')) return capabilities.bodyControl !== false
    if (logical.startsWith('brow.')) return capabilities.browControl !== false
    if (logical === 'eye.x' || logical === 'eye.y') return capabilities.gazeControl !== false
    if (logical.startsWith('eye.')) return true
    if (logical.startsWith('blink.')) return capabilities.eyeBlink !== false
    if (logical === 'mouth.open') return capabilities.mouthControl !== false
    if (logical === 'mouth.form') return capabilities.mouthForm !== false
    if (logical === 'breath') return capabilities.breathControl !== false
    return true
  }

  private protectedMotionParameters(): Set<string> {
    return new Set([
      ...DEFAULT_PROTECTED_MOTION_PARAMETERS,
      ...(this._profile?.protectedMotionParameters ?? []),
    ])
  }

  private applyBinding(value: number, binding: string | AvatarParameterBinding | undefined): number {
    if (!binding || typeof binding === 'string') return value
    const neutral = binding.neutral ?? 0
    const scale = binding.scale ?? 1
    const signed = binding.mode === 'subtract' ? -value : value
    const mapped = binding.mode === 'set' ? signed * scale : neutral + signed * scale
    return Math.max(binding.min ?? -Infinity, Math.min(binding.max ?? Infinity, mapped))
  }

  private clampLogical(logical: string, value: number): number {
    if (logical.startsWith('eye.')) return clamp(value, -1, 1)
    if (logical.startsWith('brow.')) return clamp(value, -1, 1)
    if (logical.startsWith('blink.')) return clamp(value, 0, 1)
    if (logical === 'mouth.open' || logical === 'breath') return clamp(value, 0, 1)
    if (logical === 'mouth.form') return clamp(value, -1, 1)
    if (logical.startsWith('head.')) return clamp(value, -30, 30)
    if (logical.startsWith('body.')) return clamp(value, -15, 15)
    if (logical.startsWith('tail.')) return clamp(value, -18, 18)
    return value
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
