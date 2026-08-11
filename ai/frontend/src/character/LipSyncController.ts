import type { AvatarLipSyncConfig } from './AvatarCapabilityProfile.ts'
import { AudioAnalyzer, type LipSyncDebugInfo } from './AudioAnalyzer.ts'

export const LIP_SYNC_PRIORITY = 76

export interface LipSyncFrame {
  value: number
  activityWeight: number
  speaking: boolean
}

export interface LipSyncControllerDebugInfo extends LipSyncDebugInfo {
  activityWeight: number
  speaking: boolean
  outputMouth: number
}

/** Advances the complete audio-to-mouth envelope on the render clock. */
export class LipSyncController {
  readonly analyzer = new AudioAnalyzer()
  private volume = 0
  private peak = 0
  private speaking = false
  private activityWeight = 0
  private outputMouth = 0

  configure(config: AvatarLipSyncConfig): void {
    this.analyzer.configure(config)
  }

  setEnabled(enabled: boolean): void {
    this.analyzer.setEnabled(enabled)
    if (!enabled) this.reset()
  }

  setSpeaking(speaking: boolean): void {
    this.speaking = speaking
    if (!speaking) {
      this.volume = 0
      this.peak = 0
    }
  }

  setVolume(volume: number, peak = volume): void {
    this.volume = clamp(volume, 0, 1)
    this.peak = clamp(peak, 0, 1)
  }

  update(dt: number): LipSyncFrame {
    const delta = clamp(dt, 0, 0.1)
    const targetWeight = this.speaking ? 1 : 0
    const response = 1 - Math.exp(-delta * (this.speaking ? 12 : 8))
    this.activityWeight += (targetWeight - this.activityWeight) * response
    if (!this.speaking && this.activityWeight < 0.001) this.activityWeight = 0
    // Audio stop still releases across several rendered frames, but it must
    // settle before the next 4 Hz diagnostics sample and before a reply turn
    // hands the mouth to a new speaker.
    const envelopeDelta = this.speaking ? delta : delta * 2.5
    const envelope = this.analyzer.analyze(
      this.speaking ? this.volume : 0,
      envelopeDelta,
      this.speaking ? this.peak : 0,
    )
    this.outputMouth = envelope * this.activityWeight
    return { value: this.outputMouth, activityWeight: this.activityWeight, speaking: this.speaking }
  }

  reset(): void {
    this.volume = 0
    this.peak = 0
    this.speaking = false
    this.activityWeight = 0
    this.outputMouth = 0
    this.analyzer.reset()
  }

  getDebugInfo(): LipSyncControllerDebugInfo {
    return {
      ...this.analyzer.getDebugInfo(),
      activityWeight: this.activityWeight,
      speaking: this.speaking,
      outputMouth: this.outputMouth,
    }
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
