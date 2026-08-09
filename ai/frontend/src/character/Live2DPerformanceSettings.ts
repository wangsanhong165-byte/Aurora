export type Live2DPerformanceMode = 'legacy' | 'enhanced' | 'calibration'

/** Keep high-DPI canvases inside a predictable frame-time budget. */
export const LIVE2D_RENDER_DPR_CAP = 1.25

export function resolveLive2DRenderDpr(
  devicePixelRatio: unknown,
  cap = LIVE2D_RENDER_DPR_CAP,
): number {
  const device = Number(devicePixelRatio)
  const safeCap = Number.isFinite(cap) ? Math.max(0.75, cap) : LIVE2D_RENDER_DPR_CAP
  if (!Number.isFinite(device)) return Math.min(1, safeCap)
  return Math.min(safeCap, Math.max(0.75, device))
}

export interface Live2DPerformanceSettings {
  mode: Live2DPerformanceMode
  parameterGain: number
  bodyMotionGain: number
}

export type Live2DPerformanceProfileOverrides = Record<
  string,
  Partial<Live2DPerformanceSettings>
>

const DEFAULTS: Live2DPerformanceSettings = {
  mode: 'enhanced',
  parameterGain: 1.3,
  bodyMotionGain: 1.08,
}

const clamp = (value: unknown, fallback: number, min: number, max: number) => {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback
}

export function normalizeLive2DPerformanceSettings(
  value: Partial<Live2DPerformanceSettings> | null | undefined,
  fallback: Partial<Live2DPerformanceSettings> = DEFAULTS,
): Live2DPerformanceSettings {
  const defaults = { ...DEFAULTS, ...fallback }
  const mode = value?.mode
  return {
    mode: mode === 'legacy' || mode === 'enhanced' || mode === 'calibration'
      ? mode
      : defaults.mode,
    parameterGain: clamp(value?.parameterGain, defaults.parameterGain, 0.8, 2.2),
    bodyMotionGain: clamp(value?.bodyMotionGain, defaults.bodyMotionGain, 0.6, 2),
  }
}

export function readModelPerformanceDefaults(model: string): Live2DPerformanceSettings {
  const profile = (window as any).__INITIAL_MODEL_INFO__?.avatarProfiles?.[model] ?? {}
  return normalizeLive2DPerformanceSettings({
    mode: profile.performanceMode,
    parameterGain: profile.parameterGain,
    bodyMotionGain: profile.bodyMotionGain,
  })
}

export function resolvePersistedLive2DModel(settings: Record<string, unknown>): string {
  const model = settings.live2dModel
  return typeof model === 'string' ? model.trim() : ''
}
