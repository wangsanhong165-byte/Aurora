export interface DiagnosticWaveOptions {
  durationMs?: number
  sampleRate?: number
}

export interface LipSyncDiagnosticResult {
  passed: boolean
  peakVolume: number
  peakMouth: number
  finalMouth: number
  volumeSamples: number
}

/** Builds a deterministic PCM WAV that exercises attack, sustained speech, and release. */
export function createDiagnosticWavBytes(options: DiagnosticWaveOptions = {}): Uint8Array {
  const sampleRate = Math.max(8_000, Math.floor(options.sampleRate ?? 16_000))
  const durationMs = Math.max(500, Math.floor(options.durationMs ?? 1_400))
  const sampleCount = Math.floor(sampleRate * durationMs / 1000)
  const bytes = new Uint8Array(44 + sampleCount * 2)
  const view = new DataView(bytes.buffer)
  writeAscii(bytes, 0, 'RIFF')
  view.setUint32(4, 36 + sampleCount * 2, true)
  writeAscii(bytes, 8, 'WAVE')
  writeAscii(bytes, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(bytes, 36, 'data')
  view.setUint32(40, sampleCount * 2, true)

  for (let index = 0; index < sampleCount; index += 1) {
    const elapsedMs = index / sampleRate * 1000
    const attack = clamp((elapsedMs - 90) / 80, 0, 1)
    const release = clamp((durationMs - 120 - elapsedMs) / 120, 0, 1)
    const envelope = Math.min(attack, release)
    const syllable = 0.72 + 0.28 * Math.sin(2 * Math.PI * 3.4 * index / sampleRate)
    const signal = (
      Math.sin(2 * Math.PI * 190 * index / sampleRate)
      + 0.35 * Math.sin(2 * Math.PI * 380 * index / sampleRate)
    ) / 1.35
    view.setInt16(44 + index * 2, Math.round(signal * envelope * syllable * 22_000), true)
  }
  return bytes
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return btoa(binary)
}

export class LipSyncDiagnosticProbe {
  private peakVolume = 0
  private peakMouth = 0
  private finalMouth = 1
  private volumeSamples = 0

  recordVolume(volume: number): void {
    if (!Number.isFinite(volume)) return
    this.peakVolume = Math.max(this.peakVolume, clamp(volume, 0, 1))
    this.volumeSamples += 1
  }

  recordMouth(mouth: number): void {
    if (!Number.isFinite(mouth)) return
    const value = clamp(mouth, 0, 1)
    this.peakMouth = Math.max(this.peakMouth, value)
    this.finalMouth = value
  }

  finish(): LipSyncDiagnosticResult {
    return {
      passed: (
        this.volumeSamples >= 1
        && this.peakVolume >= 0.02
        && this.peakMouth >= 0.08
        && this.finalMouth <= 0.02
      ),
      peakVolume: round(this.peakVolume),
      peakMouth: round(this.peakMouth),
      finalMouth: round(this.finalMouth),
      volumeSamples: this.volumeSamples,
    }
  }
}

function writeAscii(bytes: Uint8Array, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    bytes[offset + index] = value.charCodeAt(index)
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function round(value: number): number {
  return Math.round(value * 10_000) / 10_000
}
