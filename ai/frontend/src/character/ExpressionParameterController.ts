import type { Live2DModelAdapter } from './Live2DModelAdapter'
import type { ParameterMixer } from './ParameterMixer'

interface ExpressionPreset {
  params: Array<{ id: string; value: number; blend?: 'add' | 'multiply' | 'overwrite' }>
  parts?: Array<{ id: string; opacity: number }>
}
type ExpressionResolver = (name: string) => ExpressionPreset

interface ParamTarget { id: string; from: number; to: number; startTime: number; duration: number }

export function expressionTargetForBlend(
  value: number,
  intensity: number,
  blend: 'add' | 'multiply' | 'overwrite' = 'add',
  baseline = 0,
): number {
  const weight = Math.max(0, Math.min(1, intensity))
  if (blend === 'multiply') return baseline * (1 + (value - 1) * weight)
  if (blend === 'overwrite') return baseline + (value - baseline) * weight
  return baseline + value * weight
}

export class ParameterController {
  private readonly resolveExpression: ExpressionResolver
  private mixer: ParameterMixer | null = null
  private targets: ParamTarget[] = []
  private baselines = new Map<string, number>()
  private active = new Set<string>()
  private releasing = new Set<string>()
  private activeParts = new Set<string>()
  private values = new Map<string, number>()

  constructor(resolveExpression: ExpressionResolver) {
    this.resolveExpression = resolveExpression
  }

  attach(adapter: Live2DModelAdapter, mixer: ParameterMixer): void {
    adapter.configureMixerBaseline(mixer)
    this.mixer = mixer
    this.targets = []
    this.baselines.clear()
    this.active.clear()
    this.releasing.clear()
    this.activeParts.clear()
    this.values.clear()
  }

  detach(): void {
    this.mixer = null
    this.targets = []
    this.baselines.clear()
    this.active.clear()
    this.releasing.clear()
    this.activeParts.clear()
    this.values.clear()
  }

  private baseline(id: string): number {
    if (!this.baselines.has(id)) {
      const value = this.mixer?.getBaseline(id) ?? 0
      this.baselines.set(id, value)
      this.values.set(id, value)
    }
    return this.baselines.get(id)!
  }

  private current(id: string): number {
    return this.values.has(id) ? this.values.get(id)! : this.baseline(id)
  }

  setSmooth(id: string, to: number, duration = 300, delay = 0, now = performance.now()): void {
    const from = this.current(id)
    this.removeTargets(id)
    this.targets.push({ id, from, to, startTime: now + delay, duration: Math.max(0, duration) })
  }

  removeTargets(ids: string | string[]): void {
    const removed = new Set(typeof ids === 'string' ? [ids] : ids)
    this.targets = this.targets.filter(target => !removed.has(target.id))
  }

  getTargetCount(id: string): number { return this.targets.filter(target => target.id === id).length }
  getActiveTargetParams(): Set<string> { return new Set(this.targets.map(target => target.id)) }

  applyExpression(name: string, intensity: number, duration = 400, now = performance.now()): void {
    const preset = this.resolveExpression(name)
    const next = new Set(preset.params.map(param => param.id))
    for (const id of this.active) {
      if (next.has(id)) continue
      this.releasing.add(id)
      this.setSmooth(id, this.baseline(id), duration, 0, now)
    }
    this.active = next
    for (const param of preset.params) {
      this.releasing.delete(param.id)
      this.setSmooth(param.id, expressionTargetForBlend(
        param.value, intensity, param.blend, this.baseline(param.id),
      ), duration, 0, now)
    }

    const nextParts = new Set((preset.parts ?? []).map(part => part.id))
    if (this.mixer) {
      for (const partId of this.activeParts) {
        if (!nextParts.has(partId)) this.mixer.submitPartOpacity({
          id: `expression-part:${partId}`, partId, opacity: 0, priority: 75, persistent: true,
        })
      }
      for (const part of preset.parts ?? []) this.mixer.submitPartOpacity({
        id: `expression-part:${part.id}`,
        partId: part.id,
        opacity: part.opacity * Math.max(0, Math.min(1, intensity)),
        priority: 75,
        persistent: true,
      })
    }
    this.activeParts = nextParts
  }

  resetToNeutral(duration = 500, now = performance.now()): void {
    this.applyExpression('neutral', 1, duration, now)
  }

  update(now = performance.now()): Array<{ parameterId: string; value: number; source: string; priority: number }> {
    const completedReleases = new Set<string>()
    this.targets = this.targets.filter(target => {
      const progress = target.duration === 0 ? 1 : Math.max(0, Math.min(1, (now - target.startTime) / target.duration))
      const eased = 1 - Math.pow(1 - progress, 3)
      this.values.set(target.id, target.from + (target.to - target.from) * eased)
      if (progress >= 1 && this.releasing.has(target.id)) completedReleases.add(target.id)
      return progress < 1
    })
    const owned = new Set([...this.active, ...this.releasing])
    const output = [...owned].map(parameterId => ({
      parameterId, value: this.current(parameterId), source: 'expression', priority: 75,
    }))
    for (const id of completedReleases) this.releasing.delete(id)
    return output
  }
}
