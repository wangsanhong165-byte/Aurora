// Audio player with queue, interrupt, and volume analysis for lip sync

export type AudioPlaybackHandler = {
  onStart?: () => void
  onEnd?: () => void
  onVolume?: (volume: number) => void
}

interface QueuedAudio {
  audio: string // base64 data
  format: string
}

export class AudioPlayer {
  private audioContext: AudioContext | null = null
  private currentSource: AudioBufferSourceNode | null = null
  private analyserNode: AnalyserNode | null = null
  private handlers: AudioPlaybackHandler = {}
  private animFrameId: number | null = null
  private queue: QueuedAudio[] = []
  private _isPlaying = false
  private playbackGeneration = 0



  get isPlaying(): boolean {
    return this._isPlaying
  }

  get queuedCount(): number {
    return this.queue.length
  }

  setHandlers(h: AudioPlaybackHandler): void {
    this.handlers = h
  }

  /** Enqueue TTS audio for playback */
  enqueue(base64Audio: string, format: string): void {
    this.queue.push({ audio: base64Audio, format })
    if (!this._isPlaying) {
      this.playNext()
    }
  }

  /** Stop current playback and clear queue */
  stop(): void {
    this.playbackGeneration += 1
    this.queue = []
    this.stopCurrent()
  }

  private stopCurrent(): void {
    const source = this.currentSource
    const wasActive = this._isPlaying || Boolean(source)
    this.currentSource = null
    if (source) {
      source.onended = null
      try {
        source.stop()
      } catch {
        // Already stopped
      }
      source.disconnect()
    }
    this.analyserNode = null
    this._isPlaying = false
    this.stopVolumeAnalysis()
    if (wasActive) this.handlers.onEnd?.()
  }

  private async playNext(): Promise<void> {
    if (this.queue.length === 0) return

    const item = this.queue.shift()!
    const generation = this.playbackGeneration
    this._isPlaying = true

    try {
      const ctx = this.getContext()
      const arrayBuffer = this.base64ToArrayBuffer(item.audio)
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer)
      if (generation !== this.playbackGeneration) return

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer

      const gain = ctx.createGain()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256

      source.connect(gain)
      gain.connect(analyser)
      analyser.connect(ctx.destination)

      this.currentSource = source
      this.analyserNode = analyser

      source.onended = () => {
        if (generation !== this.playbackGeneration || this.currentSource !== source) return
        this.currentSource = null
        this.stopVolumeAnalysis()
        this._isPlaying = false

        // Play next in queue or signal end
        if (this.queue.length > 0) {
          this.playNext()
        } else {
          this.handlers.onEnd?.()
        }
      }

      this.handlers.onStart?.()
      source.start()
      this.startVolumeAnalysis()
    } catch {
      if (generation !== this.playbackGeneration) return
      this._isPlaying = false
      // Skip failed audio, try next
      if (this.queue.length > 0) {
        this.playNext()
      } else {
        this.handlers.onEnd?.()
      }
    }
  }

  /** Get current RMS volume 0–1 for lip sync */
  getCurrentVolume(): number {
    if (!this.analyserNode || !this._isPlaying) return 0
    const dataArray = new Uint8Array(this.analyserNode.frequencyBinCount)
    this.analyserNode.getByteTimeDomainData(dataArray)
    let sum = 0
    for (let i = 0; i < dataArray.length; i++) {
      sum += Math.abs(dataArray[i] - 128)
    }
    return sum / dataArray.length / 128
  }

  /** Resume AudioContext (call on first user gesture to satisfy autoplay policy) */
  async resume(): Promise<void> {
    if (!this.audioContext) {
      this.audioContext = new AudioContext()
    }
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume()
    }
  }

  async dispose(): Promise<void> {
    this.stop()
    this.handlers = {}
    const context = this.audioContext
    this.audioContext = null
    if (context && context.state !== 'closed') await context.close()
  }

  private getContext(): AudioContext {
    if (!this.audioContext) {
      this.audioContext = new AudioContext()
    }
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume().catch(() => {})
    }
    return this.audioContext
  }

  private startVolumeAnalysis(): void {
    this.stopVolumeAnalysis()
    const tick = () => {
      if (!this._isPlaying) return
      const vol = this.getCurrentVolume()
      this.handlers.onVolume?.(vol)
      this.animFrameId = requestAnimationFrame(tick)
    }
    tick()
  }

  private stopVolumeAnalysis(): void {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId)
      this.animFrameId = null
    }
  }

  private base64ToArrayBuffer(base64: string): ArrayBuffer {
    const binaryStr = atob(base64)
    const bytes = new Uint8Array(binaryStr.length)
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i)
    }
    return bytes.buffer
  }
}
