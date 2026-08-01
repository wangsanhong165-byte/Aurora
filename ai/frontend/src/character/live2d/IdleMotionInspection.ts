interface MotionCurve { Target?: string; Id?: string }
interface MotionJson { Curves?: MotionCurve[] }

const NATURAL_IDLE_PARAMETER = /^(ParamAngle|ParamBodyAngle|ParamBreath)/i

export function inspectIdleMotionChannels(motion: MotionJson): {
  parameterIds: string[]
  naturalChannelCount: number
  valid: boolean
} {
  const parameterIds = (motion.Curves ?? [])
    .filter(curve => curve.Target === 'Parameter' && typeof curve.Id === 'string')
    .map(curve => curve.Id!)
  const naturalChannelCount = parameterIds.filter(id => NATURAL_IDLE_PARAMETER.test(id)).length
  return { parameterIds, naturalChannelCount, valid: naturalChannelCount > 0 }
}
