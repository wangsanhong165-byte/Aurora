export class VoiceWaitingMotionController {
  private time = 0

  update(dt: number, activity: string, gain = 1): Record<string, number> {
    this.time += Math.max(0, dt)
    if (activity !== 'listening' && activity !== 'thinking') return {}
    const thinking = activity === 'thinking'
    const phase = this.time * (thinking ? 0.78 : 0.54)
    return {
      'head.x': Math.sin(phase) * (thinking ? 1.6 : 0.8) * gain,
      'head.y': (thinking ? -0.65 : 0.35) * gain + Math.sin(phase * 0.57) * 0.35,
      'head.z': Math.sin(phase * 0.71 + 1.2) * (thinking ? 1.25 : 0.55) * gain,
      'body.x': Math.sin(phase * 0.43) * 0.7 * gain,
      'eye.y': thinking ? 0.12 : 0.02,
    }
  }
}
