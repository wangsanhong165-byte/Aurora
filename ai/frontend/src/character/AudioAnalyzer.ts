// Audio Analyzer — extracts mouth-open values from audio volume for lip sync.
//
// Takes raw volume (0-1) from the AudioPlayer, applies smoothing and decay,
// and produces stable ParamMouthOpenY values through the ParameterMixer.
//
// Debug info exposed for the debug panel: current volume, mouth value.

export interface LipSyncDebugInfo {
  rawVolume: number
  smoothedMouth: number
  targetMouth: number
  enabled: boolean
}

export class AudioAnalyzer {
  private _currentMouthOpen = 0
  private _targetMouthOpen = 0
  private _enabled = true

  // Smoothing: higher = faster response
  private _attackFactor = 0.35    // fast attack (mouth opens quickly)
  private _releaseFactor = 0.08   // slow release (mouth closes naturally)

  // Mouth range mapping
  private _mouthRange = { min: 0, max: 0.82 }

  // Silence threshold — below this, decay kicks in
  private _silenceThreshold = 0.012
  private _decayRate = 0.16

  // Debug info
  private _debug: LipSyncDebugInfo = {
    rawVolume: 0,
    smoothedMouth: 0,
    targetMouth: 0,
    enabled: true,
  }

  setEnabled(enabled: boolean): void {
    this._enabled = enabled
    if (!enabled) {
      this._currentMouthOpen = 0
      this._targetMouthOpen = 0
    }
  }

  /** Feed raw audio volume (0-1) and get smoothed mouth-open value (0-1). */
  analyze(volume: number): number {
    this._debug.rawVolume = volume

    if (!this._enabled) {
      this._currentMouthOpen = 0
      this._debug.smoothedMouth = 0
      this._debug.targetMouth = 0
      return 0
    }

    // Map volume to target mouth open
    // Browser RMS is usually a small value (roughly 0.02-0.15), not a full
    // 0-1 envelope. A square-root curve gives quiet syllables visible motion
    // while preserving a natural ceiling for loud consonants.
    const normalized = Math.max(0, Math.min(1, volume * 6.5))
    const shaped = Math.sqrt(normalized)
    this._targetMouthOpen = this._mouthRange.min + shaped * (this._mouthRange.max - this._mouthRange.min)
    this._debug.targetMouth = this._targetMouthOpen

    // Attack/release smoothing: different rates for opening vs closing
    if (this._targetMouthOpen > this._currentMouthOpen) {
      // Opening — fast attack
      this._currentMouthOpen += (this._targetMouthOpen - this._currentMouthOpen) * this._attackFactor
    } else {
      // Closing — slower release
      this._currentMouthOpen += (this._targetMouthOpen - this._currentMouthOpen) * this._releaseFactor
    }

    // Decay to zero when silent (anti-jitter)
    if (volume < this._silenceThreshold) {
      this._currentMouthOpen *= 1 - this._decayRate
    }

    this._currentMouthOpen = Math.max(0, Math.min(1, this._currentMouthOpen))
    this._debug.smoothedMouth = this._currentMouthOpen

    return this._currentMouthOpen
  }

  /** Reset to zero (call when audio stops). */
  reset(): void {
    this._currentMouthOpen = 0
    this._targetMouthOpen = 0
    this._debug.rawVolume = 0
    this._debug.smoothedMouth = 0
    this._debug.targetMouth = 0
  }

  /** Get current debug info. */
  getDebugInfo(): LipSyncDebugInfo {
    return { ...this._debug }
  }
}
