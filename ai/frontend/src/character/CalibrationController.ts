/** Holds explicit logical-parameter overrides used only by the calibration UI. */
export class CalibrationController {
  private overrides = new Map<string, number>()
  private rawOverrides = new Map<string, number>()
  private rawBaselines = new Map<string, number>()
  private pendingRawRestores = new Map<string, number>()
  private rawPartOverrides = new Map<string, number>()
  private rawPartBaselines = new Map<string, number>()
  private pendingPartRestores = new Map<string, number>()

  set(logicalParameter: string, value: number): boolean {
    if (!logicalParameter || !Number.isFinite(value)) return false
    this.overrides.set(logicalParameter, value)
    return true
  }

  remove(logicalParameter: string): void {
    this.overrides.delete(logicalParameter)
  }

  clear(): void {
    this.overrides.clear()
    this.rawOverrides.clear()
    this.rawBaselines.clear()
    this.pendingRawRestores.clear()
    this.rawPartOverrides.clear()
    this.rawPartBaselines.clear()
    this.pendingPartRestores.clear()
  }

  values(): Record<string, number> {
    return Object.fromEntries(this.overrides)
  }

  setRaw(parameterId: string, value: number, baseline = value): boolean {
    if (!parameterId || !Number.isFinite(value)) return false
    if (!this.rawBaselines.has(parameterId)) this.rawBaselines.set(parameterId, baseline)
    this.pendingRawRestores.delete(parameterId)
    this.rawOverrides.set(parameterId, value)
    return true
  }

  clearRaw(): void {
    for (const [parameterId, baseline] of this.rawBaselines) {
      this.pendingRawRestores.set(parameterId, baseline)
    }
    this.rawOverrides.clear()
    this.rawBaselines.clear()
  }

  rawValues(): Record<string, number> { return Object.fromEntries(this.rawOverrides) }

  takeRawRestores(): Record<string, number> {
    const restores = Object.fromEntries(this.pendingRawRestores)
    this.pendingRawRestores.clear()
    return restores
  }

  setRawPart(partId: string, opacity: number, baseline: number): boolean {
    if (!partId || !Number.isFinite(opacity) || !Number.isFinite(baseline)) return false
    if (!this.rawPartBaselines.has(partId)) this.rawPartBaselines.set(partId, baseline)
    this.pendingPartRestores.delete(partId)
    this.rawPartOverrides.set(partId, Math.max(0, Math.min(1, opacity)))
    return true
  }

  clearRawParts(): void {
    for (const [partId, baseline] of this.rawPartBaselines) {
      this.pendingPartRestores.set(partId, baseline)
    }
    this.rawPartOverrides.clear()
    this.rawPartBaselines.clear()
  }

  rawPartValues(): Record<string, number> { return Object.fromEntries(this.rawPartOverrides) }

  takeRawPartRestores(): Record<string, number> {
    const restores = Object.fromEntries(this.pendingPartRestores)
    this.pendingPartRestores.clear()
    return restores
  }
}
