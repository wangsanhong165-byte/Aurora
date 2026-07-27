import type { AvatarCapabilityProfile, AvatarParameterBinding } from './AvatarCapabilityProfile'

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
      const binding = this._profile?.bindings[logical]
      const id = typeof binding === 'string' ? binding : binding?.target
      if (id) {
        const expressive = logical.startsWith('head.')
          || logical.startsWith('eye.')
          || logical.startsWith('body.')
          || logical === 'mouth.form'
        const gain = (expressive ? this.parameterGain : 1)
          * (logical.startsWith('body.') ? this.bodyMotionGain : 1)
        result[id] = this.clampLogical(logical, this.applyBinding(value * gain, binding))
      }
    }
    return result
  }
  resolveMotionParameters(entries: Record<string, number>): Record<string, number> { return this.values(entries) }

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
    if (logical.startsWith('blink.')) return clamp(value, 0, 1)
    if (logical === 'mouth.open' || logical === 'breath') return clamp(value, 0, 1)
    if (logical === 'mouth.form') return clamp(value, -1, 1)
    if (logical.startsWith('head.')) return clamp(value, -30, 30)
    if (logical.startsWith('body.')) return clamp(value, -15, 15)
    return value
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
