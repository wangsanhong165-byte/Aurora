export interface NativeMotionContribution {
  parameterId: string
  value: number
  weight: number
}

interface NativeMotionCurve {
  Target: string
  Id: string
  Segments: number[]
  FadeInTime?: number
  FadeOutTime?: number
}

interface NativeMotionJson {
  Meta?: { Duration?: number; Loop?: boolean }
  FadeInTime?: number
  FadeOutTime?: number
  Curves?: NativeMotionCurve[]
}

interface RegisteredMotion {
  json: NativeMotionJson
  duration: number
  fadeIn: number
  fadeOut: number
}

export class NativeMotionPlayer {
  private motions = new Map<string, RegisteredMotion>()
  private active: RegisteredMotion | null = null
  private activeName: string | null = null
  private elapsed = 0
  private intensity = 1

  register(name: string, json: NativeMotionJson, aliases: string[] = []): void {
    const motion: RegisteredMotion = {
      json,
      duration: Math.max(0.001, json.Meta?.Duration ?? inferDuration(json.Curves ?? [])),
      fadeIn: Math.max(0, json.FadeInTime ?? 0.25),
      fadeOut: Math.max(0, json.FadeOutTime ?? 0.35),
    }
    for (const key of [name, ...aliases]) {
      if (key) this.motions.set(key.toLowerCase(), motion)
    }
  }

  has(name: string): boolean {
    return this.motions.has(name.toLowerCase())
  }

  list(): string[] {
    return [...this.motions.keys()]
  }

  play(name: string, intensity = 1): boolean {
    const motion = this.motions.get(name.toLowerCase())
    if (!motion) return false
    this.active = motion
    this.activeName = name
    this.elapsed = 0
    this.intensity = clamp(intensity, 0, 2)
    return true
  }

  stop(): void {
    this.active = null
    this.activeName = null
    this.elapsed = 0
  }

  update(dt: number): { contributions: NativeMotionContribution[]; done: boolean } {
    if (!this.active) return { contributions: [], done: true }
    this.elapsed += Math.max(0, dt)
    const motion = this.active
    const fadeInWeight = motion.fadeIn <= 0 ? 1 : smoothstep(this.elapsed / motion.fadeIn)
    const remaining = motion.duration - this.elapsed
    const fadeOutWeight = motion.fadeOut <= 0 ? 1 : smoothstep(remaining / motion.fadeOut)
    const weight = clamp(Math.min(fadeInWeight, fadeOutWeight) * this.intensity, 0, 1)
    const contributions = (motion.json.Curves ?? [])
      .filter(curve => curve.Target === 'Parameter')
      .map(curve => ({
        parameterId: curve.Id,
        value: sampleCurve(curve.Segments, Math.min(this.elapsed, motion.duration)),
        weight: curveWeight(curve, this.elapsed, motion.duration) * weight,
      }))
    const done = this.elapsed >= motion.duration
    if (done) this.stop()
    return { contributions, done }
  }

  getDebugState(): Record<string, unknown> {
    return {
      name: this.activeName,
      elapsed: this.elapsed,
      available: this.motions.size,
    }
  }
}

export function sampleCurve(segments: number[], time: number): number {
  if (segments.length < 2) return 0
  let previousTime = segments[0]
  let previousValue = segments[1]
  let index = 2
  while (index < segments.length) {
    const segmentType = segments[index++]
    if (segmentType === 0) {
      const nextTime = segments[index++]
      const nextValue = segments[index++]
      if (time <= nextTime) return lerp(previousValue, nextValue, ratio(time, previousTime, nextTime))
      previousTime = nextTime
      previousValue = nextValue
    } else if (segmentType === 1) {
      const c1Time = segments[index++]
      const c1Value = segments[index++]
      const c2Time = segments[index++]
      const c2Value = segments[index++]
      const nextTime = segments[index++]
      const nextValue = segments[index++]
      if (time <= nextTime) {
        const t = solveBezierTime(time, previousTime, c1Time, c2Time, nextTime)
        return cubic(previousValue, c1Value, c2Value, nextValue, t)
      }
      previousTime = nextTime
      previousValue = nextValue
    } else if (segmentType === 2) {
      const nextTime = segments[index++]
      const nextValue = segments[index++]
      if (time <= nextTime) return previousValue
      previousTime = nextTime
      previousValue = nextValue
    } else if (segmentType === 3) {
      const nextTime = segments[index++]
      const nextValue = segments[index++]
      if (time <= nextTime) return nextValue
      previousTime = nextTime
      previousValue = nextValue
    } else {
      break
    }
  }
  return previousValue
}

function curveWeight(curve: NativeMotionCurve, elapsed: number, duration: number): number {
  const fadeIn = curve.FadeInTime
  const fadeOut = curve.FadeOutTime
  const inWeight = fadeIn === undefined || fadeIn < 0 ? 1 : smoothstep(elapsed / Math.max(.001, fadeIn))
  const outWeight = fadeOut === undefined || fadeOut < 0
    ? 1 : smoothstep((duration - elapsed) / Math.max(.001, fadeOut))
  return clamp(Math.min(inWeight, outWeight), 0, 1)
}
function inferDuration(curves: NativeMotionCurve[]): number {
  let duration = 0
  for (const curve of curves) {
    const values = curve.Segments
    for (let index = 0; index < values.length; index += 1) {
      if (Number.isFinite(values[index])) duration = Math.max(duration, values[index])
    }
  }
  return duration || 1
}
function solveBezierTime(target: number, p0: number, p1: number, p2: number, p3: number): number {
  let low = 0
  let high = 1
  for (let index = 0; index < 10; index += 1) {
    const mid = (low + high) / 2
    if (cubic(p0, p1, p2, p3, mid) < target) low = mid
    else high = mid
  }
  return (low + high) / 2
}
function cubic(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const u = 1 - t
  return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3
}
function ratio(value: number, min: number, max: number): number {
  return clamp((value - min) / Math.max(.000001, max - min), 0, 1)
}
function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount
}
function smoothstep(value: number): number {
  const t = clamp(value, 0, 1)
  return t * t * (3 - 2 * t)
}
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
