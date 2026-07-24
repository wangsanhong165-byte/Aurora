import type { AvatarCapabilityProfile, AvatarParameterBinding } from './AvatarCapabilityProfile'

/** Resolves logical performance keys to the current model's Cubism IDs. */
export class AvatarParameterResolver {
  private _profile: AvatarCapabilityProfile | undefined

  setProfile(profile: AvatarCapabilityProfile | undefined): void { this._profile = profile }
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
      if (id) result[id] = this.applyBinding(value, binding)
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
}
