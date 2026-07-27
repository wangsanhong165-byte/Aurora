// Audio Recorder — captures microphone input and streams to Runtime
// Uses MediaStream API for audio capture

export type RecorderState = 'idle' | 'recording' | 'error' | 'unsupported'

export interface RecorderCallbacks {
  onData?: (samples: Float32Array, sampleRate: number) => void
  onEnd?: () => void
  onError?: (error: string) => void
  onStateChange?: (state: RecorderState) => void
}

export class AudioRecorder {
  private stream: MediaStream | null = null
  private audioContext: AudioContext | null = null
  private processor: ScriptProcessorNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private _state: RecorderState = 'idle'
  private callbacks: RecorderCallbacks = {}
  private sampleRate = 16000
  private bufferSize = 2048

  // VAD (Voice Activity Detection) parameters
  private vadThreshold = 0.02         // RMS threshold for silence detection (calibrated for typical room noise)
  private silenceTimeout = 1500       // ms of continuous silence before auto-stop
  private maxDuration = 30000         // max recording duration in ms (30s safety limit)
  private silenceStartTime = 0        // timestamp when silence first detected
  private recordingStartTime = 0      // timestamp when recording started
  private vadCheckTimer: ReturnType<typeof setInterval> | null = null
  private _stopped = false            // guard against double-stop

  /** Current recorder state */
  get state(): RecorderState {
    return this._state
  }

  setCallbacks(cb: RecorderCallbacks): void {
    this.callbacks = cb
  }

  /** Compute RMS energy of a float32 audio buffer */
  private computeRMS(samples: Float32Array): number {
    let sum = 0
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i]
    }
    return Math.sqrt(sum / samples.length)
  }

  /** Request microphone access and start recording */
  async start(): Promise<boolean> {
    if (this._state === 'recording') return true
    this._stopped = false

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: this.sampleRate,
        },
      })

      this.audioContext = new AudioContext({ sampleRate: this.sampleRate })
      this.source = this.audioContext.createMediaStreamSource(this.stream)
      this.processor = this.audioContext.createScriptProcessor(this.bufferSize, 1, 1)

      this.silenceStartTime = 0
      this.recordingStartTime = Date.now()

      this.processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0)
        const samples = new Float32Array(input)
        this.callbacks.onData?.(samples, this.audioContext!.sampleRate)

        // VAD: track silence duration
        const rms = this.computeRMS(samples)
        if (rms < this.vadThreshold) {
          if (this.silenceStartTime === 0) {
            this.silenceStartTime = Date.now()
          }
        } else {
          this.silenceStartTime = 0  // reset on sound
        }
      }

      this.source.connect(this.processor)
      this.processor.connect(this.audioContext.destination)

      this._state = 'recording'
      this.callbacks.onStateChange?.('recording')

      // Periodic VAD check (every 200ms)
      this.vadCheckTimer = setInterval(() => {
        if (this._state !== 'recording') return
        // Check for silence timeout
        if (this.silenceStartTime > 0) {
          const elapsed = Date.now() - this.silenceStartTime
          if (elapsed >= this.silenceTimeout) {
            this.stop()
          }
        }
        // Check for max duration
        if (Date.now() - this.recordingStartTime >= this.maxDuration) {
          this.stop()
        }
      }, 200)

      return true

    } catch (err) {
      this._state = 'error'
      const msg = err instanceof Error ? err.message : 'Unknown error'
      this.callbacks.onError?.(msg)
      this.callbacks.onStateChange?.('error')
      return false
    }
  }

  /** Stop recording and release microphone */
  stop(): void {
    if (this._stopped) return
    this._stopped = true

    // Clear timers
    if (this.vadCheckTimer) {
      clearInterval(this.vadCheckTimer)
      this.vadCheckTimer = null
    }

    if (this.processor) {
      this.processor.disconnect()
      this.processor = null
    }
    if (this.source) {
      this.source.disconnect()
      this.source = null
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop())
      this.stream = null
    }
    if (this.audioContext) {
      this.audioContext.close()
      this.audioContext = null
    }

    this._state = 'idle'
    this.silenceStartTime = 0
    this.callbacks.onEnd?.()
    this.callbacks.onStateChange?.('idle')
  }

  /** Check if microphone is supported */
  static isSupported(): boolean {
    return !!(navigator.mediaDevices?.getUserMedia)
  }
}
