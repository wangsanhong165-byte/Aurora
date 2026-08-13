export interface AccessoryParameterValue {
  id: string
  value: number
}

export interface AccessoryParameterState {
  value: number
  labels: string[]
}

/** Collapse overlapping component presets into one state owner per Cubism parameter. */
export function mergeAccessoryParameterState(
  parts: Readonly<Record<string, string>>,
  state: Readonly<Record<string, boolean>>,
  resolve: (expression: string) => { params: AccessoryParameterValue[] } | undefined,
): Map<string, AccessoryParameterState> {
  const merged = new Map<string, AccessoryParameterState>()
  for (const [label, expression] of Object.entries(parts)) {
    if (!state[label]) continue
    for (const parameter of resolve(expression)?.params ?? []) {
      if (parameter.value === 0) continue
      const previous = merged.get(parameter.id)
      if (!previous) {
        merged.set(parameter.id, { value: parameter.value, labels: [label] })
        continue
      }
      if (!previous.labels.includes(label)) previous.labels.push(label)
      if (Math.abs(parameter.value) > Math.abs(previous.value)) previous.value = parameter.value
    }
  }
  return merged
}

/** Resolve the complete persistent accessory layer, including baseline restores. */
export function resolveAccessoryParameterState(
  parts: Readonly<Record<string, string>>,
  state: Readonly<Record<string, boolean>>,
  resolve: (expression: string) => { params: AccessoryParameterValue[] } | undefined,
  baseline: (parameterId: string) => number,
): Map<string, AccessoryParameterState> {
  const active = mergeAccessoryParameterState(parts, state, resolve)
  const owned = new Set<string>()
  for (const expression of Object.values(parts)) {
    for (const parameter of resolve(expression)?.params ?? []) {
      // Zero-valued roots can be animation inputs rather than visibility
      // switches (shirone's cat tail is one), so accessories must not claim them.
      if (parameter.value !== 0) owned.add(parameter.id)
    }
  }
  return new Map([...owned].map(parameterId => [
    parameterId,
    active.get(parameterId) ?? { value: baseline(parameterId), labels: [] },
  ]))
}
