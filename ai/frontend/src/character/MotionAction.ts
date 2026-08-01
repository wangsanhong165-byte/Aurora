import type { MotionKeyframe, MotionPreset } from './MotionArbiter'

export const MOTION_PRIMITIVES = [
  'nod',
  'tilt_left',
  'tilt_right',
  'lean_forward',
  'lean_back',
  'sway',
  'look_left',
  'look_right',
  'breathe',
  'shrug',
] as const

export type MotionPrimitive = typeof MOTION_PRIMITIVES[number]

export interface MotionActionStep {
  atMs: number
  durationMs: number
  primitive: MotionPrimitive
  intensity: number
}

export interface MotionPlan {
  durationMs: number
  steps: MotionActionStep[]
}

export interface MotionActionDefinition extends MotionPlan {
  version: 1
  id: string
  name: string
  recoveryMs?: number
}

export type Live2DActionsByModel = Record<string, MotionActionDefinition[]>

export interface MotionPlanValidation {
  ok: boolean
  errors: string[]
  plan?: MotionPlan
}

type PrimitiveFrame = {
  progress: number
  values: Record<string, number>
}

const MAX_ACTION_DURATION_MS = 8_000
const MAX_STEPS = 16

export function validateMotionPlan(value: unknown): MotionPlanValidation {
  const errors: string[] = []
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { ok: false, errors: ['motion plan must be an object'] }
  }
  const record = value as Record<string, unknown>
  if ('keyframes' in record || 'parameter' in record || 'parameters' in record) {
    errors.push('renderer parameters and keyframes are not allowed in a motion plan')
  }
  const durationMs = finiteNumber(record.durationMs)
  if (durationMs === null || durationMs < 300 || durationMs > MAX_ACTION_DURATION_MS) {
    errors.push(`durationMs must be between 300 and ${MAX_ACTION_DURATION_MS}`)
  }
  if (!Array.isArray(record.steps) || record.steps.length < 1 || record.steps.length > MAX_STEPS) {
    errors.push(`steps must contain between 1 and ${MAX_STEPS} entries`)
  }

  const steps: MotionActionStep[] = []
  if (Array.isArray(record.steps)) {
    record.steps.slice(0, MAX_STEPS + 1).forEach((raw, index) => {
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        errors.push(`steps[${index}] must be an object`)
        return
      }
      const step = raw as Record<string, unknown>
      if ('parameter' in step || 'value' in step || 'keyframes' in step) {
        errors.push(`steps[${index}] cannot contain renderer parameters or keyframes`)
      }
      const primitive = typeof step.primitive === 'string' ? step.primitive : ''
      if (!MOTION_PRIMITIVES.includes(primitive as MotionPrimitive)) {
        errors.push(`steps[${index}].primitive is not allowed`)
      }
      const atMs = finiteNumber(step.atMs)
      const stepDuration = finiteNumber(step.durationMs)
      const intensity = finiteNumber(step.intensity)
      if (atMs === null || atMs < 0 || (durationMs !== null && atMs > durationMs)) {
        errors.push(`steps[${index}].atMs is outside the action duration`)
      }
      if (stepDuration === null || stepDuration < 120 || stepDuration > 2_500) {
        errors.push(`steps[${index}].durationMs must be between 120 and 2500`)
      }
      if (
        atMs !== null
        && stepDuration !== null
        && durationMs !== null
        && atMs + stepDuration > durationMs
      ) {
        errors.push(`steps[${index}] ends after the action duration`)
      }
      if (intensity === null || intensity < 0 || intensity > 1) {
        errors.push(`steps[${index}].intensity must be between 0 and 1`)
      }
      if (
        MOTION_PRIMITIVES.includes(primitive as MotionPrimitive)
        && atMs !== null
        && stepDuration !== null
        && intensity !== null
      ) {
        steps.push({
          atMs: Math.round(atMs),
          durationMs: Math.round(stepDuration),
          primitive: primitive as MotionPrimitive,
          intensity,
        })
      }
    })
  }

  return {
    ok: errors.length === 0,
    errors,
    plan: errors.length === 0 && durationMs !== null
      ? { durationMs: Math.round(durationMs), steps }
      : undefined,
  }
}

export function normalizeMotionAction(value: unknown): MotionActionDefinition {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Action must be an object')
  }
  const record = value as Record<string, unknown>
  const validation = validateMotionPlan(record)
  if (!validation.ok || !validation.plan) {
    throw new Error(validation.errors.join('; '))
  }
  const id = normalizeActionId(record.id)
  const name = typeof record.name === 'string' && record.name.trim()
    ? record.name.trim().slice(0, 48)
    : id
  const recoveryMs = finiteNumber(record.recoveryMs)
  return {
    version: 1,
    id,
    name,
    durationMs: validation.plan.durationMs,
    steps: validation.plan.steps,
    ...(recoveryMs !== null
      ? { recoveryMs: Math.round(clamp(recoveryMs, 300, 600)) }
      : {}),
  }
}

export function normalizeMotionActions(value: unknown): MotionActionDefinition[] {
  if (!Array.isArray(value)) return []
  const actions: MotionActionDefinition[] = []
  const ids = new Set<string>()
  for (const raw of value.slice(0, 32)) {
    try {
      const action = normalizeMotionAction(raw)
      if (ids.has(action.id)) continue
      ids.add(action.id)
      actions.push(action)
    } catch {
      // Invalid persisted/imported actions are omitted rather than entering runtime.
    }
  }
  return actions
}

export function compileMotionAction(action: MotionActionDefinition): MotionPreset {
  const keyframes: MotionKeyframe[] = []
  for (const step of action.steps) {
    for (const frame of primitiveFrames(step.primitive)) {
      const time = Math.round(step.atMs + step.durationMs * frame.progress)
      for (const [parameter, value] of Object.entries(frame.values)) {
        keyframes.push({
          time: clamp(time, 0, action.durationMs),
          parameter,
          value: value * step.intensity,
        })
      }
    }
  }
  return {
    name: action.id,
    duration: action.durationMs,
    recoveryMs: action.recoveryMs ?? 420,
    keyframes,
  }
}

export function compileMotionPlan(
  plan: unknown,
  id: string,
  name = 'AI 动作',
): MotionPreset | null {
  const validation = validateMotionPlan(plan)
  if (!validation.ok || !validation.plan) return null
  return compileMotionAction({
    version: 1,
    id: normalizeActionId(id),
    name,
    ...validation.plan,
  })
}

function primitiveFrames(primitive: MotionPrimitive): PrimitiveFrame[] {
  switch (primitive) {
    case 'nod':
      return [
        { progress: 0, values: { 'head.y': 0 } },
        { progress: .28, values: { 'head.y': -9 } },
        { progress: .62, values: { 'head.y': 5 } },
        { progress: 1, values: { 'head.y': 0 } },
      ]
    case 'tilt_left':
      return axisFrames('head.z', -12)
    case 'tilt_right':
      return axisFrames('head.z', 12)
    case 'lean_forward':
      return combinedFrames({ 'body.y': 6, 'head.y': 3 })
    case 'lean_back':
      return combinedFrames({ 'body.y': -5, 'head.y': -2 })
    case 'sway':
      return [
        { progress: 0, values: { 'body.x': 0, 'head.z': 0 } },
        { progress: .3, values: { 'body.x': -7, 'head.z': -4 } },
        { progress: .7, values: { 'body.x': 7, 'head.z': 4 } },
        { progress: 1, values: { 'body.x': 0, 'head.z': 0 } },
      ]
    case 'look_left':
      return combinedFrames({ 'eye.x': -.75, 'head.x': -7 })
    case 'look_right':
      return combinedFrames({ 'eye.x': .75, 'head.x': 7 })
    case 'breathe':
      return axisFrames('body.y', 3.5)
    case 'shrug':
      return combinedFrames({ 'body.y': 4.5, 'head.z': 3 })
  }
}

function axisFrames(parameter: string, peak: number): PrimitiveFrame[] {
  return combinedFrames({ [parameter]: peak })
}

function combinedFrames(values: Record<string, number>): PrimitiveFrame[] {
  const zero = Object.fromEntries(Object.keys(values).map(key => [key, 0]))
  return [
    { progress: 0, values: zero },
    { progress: .45, values },
    { progress: 1, values: zero },
  ]
}

function normalizeActionId(value: unknown): string {
  const raw = typeof value === 'string' ? value.trim().toLowerCase() : ''
  const normalized = raw.replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)
  if (!normalized) throw new Error('Action id is required')
  return normalized
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
