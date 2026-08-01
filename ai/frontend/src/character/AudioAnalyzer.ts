import type { AvatarLipSyncConfig } from './AvatarCapabilityProfile'

export interface LipSyncDebugInfo {
  rawVolume: number
  peakVolume: number
  smoothedMouth: number
  targetMouth: number
  enabled: boolean
  gated: boolean
}

const DEFAULT_CONFIG: Required<AvatarLipSyncConfig> = {
  min: 0,
  max: 0.82,
  inputGain: 6.5,
  noiseGate: 0.012,
  attackMs: 42,
  releaseMs: 145,
  peakBoost: 0.16,
}

/** Converts measured browser audio energy into a frame-rate independent mouth envelope. */
export class AudioAnalyzer {
  private current = 0
  private target = 0
  private enabled = true
  private config = { ...DEFAULT_CONFIG }
  private debug: LipSyncDebugInfo = {
    rawVolume: 0,
    peakVolume: 0,
    smoothedMouth: 0,
    targetMouth: 0,
    enabled: true,
    gated: true,
  }

  configure(config: AvatarLipSyncConfig): void {
    const min = clamp(config.min ?? this.config.min, 0, 1)
    this.config = {
      min,
      max: clamp(config.max ?? this.config.max, min, 1),
      inputGain: Math.max(0.1, config.inputGain ?? this.config.inputGain),
      noiseGate: Math.max(0, config.noiseGate ?? this.config.noiseGate),
      attackMs: Math.max(1, config.attackMs ?? this.config.attackMs),
      releaseMs: Math.max(1, config.releaseMs ?? this.config.releaseMs),
      peakBoost: Math.max(0, config.peakBoost ?? this.config.peakBoost),
    }
    this.current = clamp(this.current, min, this.config.max)
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled
    this.debug.enabled = enabled
    if (!enabled) this.reset()
  }

  analyze(volume: number, dt = 1 / 60, peak = volume): number {
    const raw = clamp(volume, 0, 1)
    const measuredPeak = clamp(peak, 0, 1)
    const gated = raw < this.config.noiseGate && measuredPeak < this.config.noiseGate
    this.debug.rawVolume = raw
    this.debug.peakVolume = measuredPeak
    this.debug.gated = gated
    if (!this.enabled) return 0

    if (gated) {
      this.target = this.config.min
    } else {
      const energy = clamp((raw - this.config.noiseGate) * this.config.inputGain, 0, 1)
      const transient = Math.max(0, measuredPeak - raw) * this.config.peakBoost
      const shaped = clamp(Math.sqrt(energy) + transient, 0, 1)
      this.target = this.config.min
        + shaped * (this.config.max - this.config.min)
    }

    const responseMs = this.target > this.current
      ? this.config.attackMs
      : this.config.releaseMs
    const response = 1 - Math.exp(-Math.max(0, dt) * 1000 / responseMs)
    this.current += (this.target - this.current) * response
    if (gated && Math.abs(this.current - this.config.min) < 0.001) {
      this.current = this.config.min
    }
    this.current = clamp(this.current, this.config.min, this.config.max)
    this.debug.targetMouth = this.target
    this.debug.smoothedMouth = this.current
    return this.current
  }

  reset(): void {
    this.current = 0
    this.target = 0
    this.debug.rawVolume = 0
    this.debug.peakVolume = 0
    this.debug.smoothedMouth = 0
    this.debug.targetMouth = 0
    this.debug.gated = true
  }

  getDebugInfo(): LipSyncDebugInfo {
    return { ...this.debug }
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
