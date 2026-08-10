export interface EmbodiedTrackingSample {
  'eye.x': number
  'eye.y': number
  'head.x': number
  'head.y': number
  'head.z': number
  'body.x': number
  'body.y': number
  'body.z': number
}

interface SpringAxis {
  value: number
  velocity: number
}

/**
 * Converts a normalized pointer target into a hierarchical gaze posture.
 *
 * Eyes acquire first, the head follows, and the torso is recruited only by
 * larger targets.  The torso uses a second-order spring so it carries weight
 * through direction changes instead of remaining a scaled copy of the head.
 */
export class EmbodiedTrackingController {
  private targetX = 0
  private targetY = 0
  private previousTargetX = 0
  private previousTargetY = 0
  private targetVelocityX = 0
  private targetVelocityY = 0
  private eyeX = 0
  private eyeY = 0
  private headX = 0
  private headY = 0
  private readonly torsoX: SpringAxis = { value: 0, velocity: 0 }
  private readonly torsoY: SpringAxis = { value: 0, velocity: 0 }

  setTarget(x: number, y: number): void {
    this.targetX = clamp(x, -1, 1)
    this.targetY = clamp(y, -1, 1)
  }

  release(): void {
    this.setTarget(0, 0)
  }

  reset(): void {
    this.targetX = 0
    this.targetY = 0
    this.previousTargetX = 0
    this.previousTargetY = 0
    this.targetVelocityX = 0
    this.targetVelocityY = 0
    this.eyeX = 0
    this.eyeY = 0
    this.headX = 0
    this.headY = 0
    this.torsoX.value = 0
    this.torsoX.velocity = 0
    this.torsoY.value = 0
    this.torsoY.velocity = 0
  }

  getDebugState(): Record<string, unknown> {
    return {
      target: { x: this.targetX, y: this.targetY },
      targetVelocity: { x: this.targetVelocityX, y: this.targetVelocityY },
      pose: this.sample(),
      torsoVelocity: { x: this.torsoX.velocity, y: this.torsoY.velocity },
    }
  }

  update(dt: number): EmbodiedTrackingSample {
    const delta = clamp(dt, 0, 0.05)
    if (delta <= 0) return this.sample()

    const observedVelocityX = clamp((this.targetX - this.previousTargetX) / delta, -3.2, 3.2)
    const observedVelocityY = clamp((this.targetY - this.previousTargetY) / delta, -3.2, 3.2)
    const velocityBlend = 1 - Math.exp(-delta * 18)
    this.targetVelocityX += (observedVelocityX - this.targetVelocityX) * velocityBlend
    this.targetVelocityY += (observedVelocityY - this.targetVelocityY) * velocityBlend
    this.previousTargetX = this.targetX
    this.previousTargetY = this.targetY

    const eyeTargetX = clamp(this.targetX + this.targetVelocityX * 0.035, -1, 1)
    const eyeTargetY = clamp(this.targetY + this.targetVelocityY * 0.025, -1, 1)
    this.eyeX = approach(this.eyeX, eyeTargetX, delta, 24)
    this.eyeY = approach(this.eyeY, eyeTargetY, delta, 22)

    const headInputX = softDeadZone(this.targetX + this.targetVelocityX * 0.018, 0.045)
    const headInputY = softDeadZone(this.targetY + this.targetVelocityY * 0.014, 0.055)
    this.headX = approach(this.headX, headInputX, delta, 13.5)
    this.headY = approach(this.headY, headInputY, delta, 12.2)

    const torsoTargetX = softDeadZone(this.targetX, 0.27) * 4.4
    const torsoTargetY = softDeadZone(this.targetY, 0.3) * 3.2
    stepSpring(this.torsoX, torsoTargetX, delta, 1.12, 0.84)
    stepSpring(this.torsoY, torsoTargetY, delta, 1.02, 0.9)

    return this.sample()
  }

  private sample(): EmbodiedTrackingSample {
    return {
      'eye.x': this.eyeX * 0.85,
      'eye.y': this.eyeY * 0.7,
      'head.x': this.headX * 15,
      'head.y': this.headY * 10,
      'head.z': this.headX * 3.6 - this.torsoX.value * 0.18,
      'body.x': this.torsoX.value,
      'body.y': this.torsoY.value,
      // Opposing axial load prevents shoulders and head from rotating as one
      // flat board. The model's own physics expands this into chest/clothing.
      'body.z': -this.torsoX.value * 0.34,
    }
  }
}

function approach(value: number, target: number, dt: number, response: number): number {
  return value + (target - value) * (1 - Math.exp(-dt * response))
}

function softDeadZone(value: number, threshold: number): number {
  const magnitude = Math.abs(value)
  if (magnitude <= threshold) return 0
  const normalized = (magnitude - threshold) / (1 - threshold)
  const eased = normalized * normalized * (3 - 2 * normalized)
  return Math.sign(value) * eased
}

function stepSpring(
  axis: SpringAxis,
  target: number,
  dt: number,
  frequencyHz: number,
  dampingRatio: number,
): void {
  const omega = Math.PI * 2 * frequencyHz
  const acceleration = (target - axis.value) * omega * omega
    - 2 * dampingRatio * omega * axis.velocity
  axis.velocity += acceleration * dt
  axis.value += axis.velocity * dt
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
