/** Holds explicit logical-parameter overrides used only by the calibration UI. */
export class CalibrationController {
  private overrides = new Map<string, number>()

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
  }

  values(): Record<string, number> {
    return Object.fromEntries(this.overrides)
  }
}
