import { createSeededRandom } from './SeededRandom.ts'

type WaitingActivity = 'listening' | 'thinking'
type WaitingTemplate = 'slow-sway' | 'figure-eight' | 'curious-lean' | 'contained-tension'

export class VoiceWaitingMotionController {
  private time = 0
  private activity: WaitingActivity | null = null
  private template: WaitingTemplate = 'slow-sway'
  private release = 0
  private last: Record<string, number> = {}
  private readonly random: () => number

  constructor(seed = 1) {
    this.random = createSeededRandom(seed)
  }

  update(dt: number, activity: string, gain = 1): Record<string, number> {
    const delta = Math.max(0, dt)
    this.time += delta
    if (activity === 'listening' || activity === 'thinking') {
      if (this.activity !== activity) {
        this.activity = activity
        this.template = pickTemplate(activity, this.random)
        this.release = 1
      }
      this.last = sampleTemplate(this.template, this.time, gain)
      return { ...this.last }
    }

    if (this.activity) {
      this.activity = null
      this.release = 1
    }
    if (this.release <= .002) {
      this.release = 0
      this.last = {}
      return {}
    }
    this.release *= Math.exp(-delta / .24)
    if (this.release <= .002) {
      this.last = {}
      return {}
    }
    return Object.fromEntries(
      Object.entries(this.last).map(([key, value]) => [key, value * this.release]),
    )
  }
}

function pickTemplate(activity: WaitingActivity, random: () => number): WaitingTemplate {
  const pool: WaitingTemplate[] = activity === 'thinking'
    ? ['figure-eight', 'curious-lean', 'contained-tension']
    : ['slow-sway', 'curious-lean', 'figure-eight']
  return pool[Math.floor(random() * pool.length)]
}

function sampleTemplate(
  template: WaitingTemplate,
  time: number,
  gain: number,
): Record<string, number> {
  if (template === 'figure-eight') return {
    'head.x': Math.sin(time * .82) * 1.25 * gain,
    'head.y': Math.sin(time * 1.64) * .65 * gain - .35 * gain,
    'head.z': Math.cos(time * .82) * 1.2 * gain,
    'body.x': Math.sin(time * .41) * .65 * gain,
    'eye.y': .1,
  }
  if (template === 'curious-lean') return {
    'head.x': Math.sin(time * .55) * .75 * gain,
    'head.y': .55 * gain + Math.sin(time * .43) * .28 * gain,
    'head.z': 1.15 * gain + Math.sin(time * .68) * .55 * gain,
    'body.x': Math.sin(time * .31) * .6 * gain,
    'body.y': .55 * gain,
    'eye.y': .06,
  }
  if (template === 'contained-tension') return {
    'head.x': Math.sin(time * 1.35) * .55 * gain,
    'head.y': -.75 * gain + Math.sin(time * .72) * .22 * gain,
    'head.z': Math.cos(time * 1.08) * .8 * gain,
    'body.x': Math.sin(time * .64) * .42 * gain,
    'body.y': -.48 * gain,
    'eye.y': .12,
  }
  return {
    'head.x': Math.sin(time * .52) * .72 * gain,
    'head.y': .25 * gain + Math.sin(time * .29) * .25 * gain,
    'head.z': Math.sin(time * .41 + 1.2) * .58 * gain,
    'body.x': Math.sin(time * .25) * .62 * gain,
    'eye.y': .02,
  }
}
