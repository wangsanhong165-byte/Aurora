// WebSocket Client — connects to Companion Runtime via V2 Transport Protocol

import { eventBus } from '../core/event-bus'
import type { InboundMessage, OutboundMessage } from './protocol'

export class RuntimeClient {
  private ws: WebSocket | null = null
  private url: string
  private reconnectBaseDelay = 1000   // start at 1s
  private reconnectMaxDelay = 30000  // cap at 30s
  private reconnectAttempts = 0
  private reconnectMaxAttempts = 20  // give up after ~20 attempts (~8 min total)
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private intentionalClose = false
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private pongPending = false
  private _unsubAvatarSend: (() => void) | null = null

  constructor(url: string) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return
    this.intentionalClose = false

    // Listen for avatar send requests from AvatarController
    this._unsubAvatarSend = eventBus.on('avatar:send', (data) => {
      this.send(data as unknown as OutboundMessage)
    })

    eventBus.emit('connection:change', { connected: false })

    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      eventBus.emit('connection:change', { connected: true })
      this.startPing()
    }

    this.ws.onclose = () => {
      eventBus.emit('connection:change', { connected: false })
      this.stopPing()
      if (!this.intentionalClose) {
        this.scheduleReconnect()
      }
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as InboundMessage
        this.dispatch(data)
      } catch {
        // Ignore malformed messages
      }
    }
  }

  disconnect(): void {
    this.intentionalClose = true
    this.reconnectAttempts = this.reconnectMaxAttempts // prevent reconnect
    this.stopPing()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this._unsubAvatarSend) {
      this._unsubAvatarSend()
      this._unsubAvatarSend = null
    }
    this.ws?.close()
    this.ws = null
    eventBus.emit('connection:change', { connected: false })
  }

  send(msg: OutboundMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  sendText(text: string): void {
    this.send({ type: 'text_input', text })
  }

  sendInterrupt(): void {
    this.send({ type: 'interrupt' })
  }

  sendCommand(action: string, params: Record<string, unknown> = {}): void {
    this.send({ type: 'command', action, params })
  }

  sendAudioSamples(samples: Float32Array, sampleRate: number): void {
    this.send({ type: 'audio_input', samples: Array.from(samples), sample_rate: sampleRate })
  }

  sendAudioEnd(): void {
    this.send({ type: 'audio_end' })
  }

  private dispatch(data: InboundMessage): void {
    switch (data.type) {
      // Session lifecycle
      case 'session':
        if (data.status === 'init') {
          eventBus.emit('connection:change', { connected: true })
        }
        break

      // Pipeline state changes
      case 'runtime_status':
        eventBus.emit('runtime:status', {
          status: data.state,
          message: data.message,
        })
        if (data.state === 'speaking') {
          eventBus.emit('character:activity', { activity: 'speaking' })
        } else if (data.state === 'processing') {
          eventBus.emit('character:activity', { activity: 'thinking' })
        }
        // Pipeline idle is not playback idle: audio may still be queued.
        break

      // Assistant reply
      case 'assistant_message':
        eventBus.emit('runtime:message', {
          text: data.text,
          reasoning: data.reasoning,
          segments: data.segments,
        })
        break

      // Streaming chunk
      case 'assistant_chunk':
        eventBus.emit('runtime:chunk', { text: data.text, delta: data.delta })
        break

      // TTS lifecycle
      case 'tts_start':
        eventBus.emit('runtime:tts_start', { format: data.format, sequence: data.sequence })
        eventBus.emit('character:activity', { activity: 'speaking' })
        break

      case 'tts_audio':
        eventBus.emit('audio:play', {
          audio: data.data,
          format: data.format,
          volumeArray: data.volumes,
        })
        break

      case 'tts_end':
        eventBus.emit('runtime:tts_end', { reason: data.reason })
        break

      // Character state (unified)
      case 'character_state':
        eventBus.emit('runtime:character_state', {
          activity: data.activity,
          emotion: data.emotion,
          intensity: data.intensity,
          expression: data.expression,
          motion: data.motion,
          behavior: data.behavior,
          attention: data.attention,
          energy: data.energy,
          durationMs: data.duration_ms,
        })
        break

      // Character update (V2 model-ready presentation)
      case 'character_update':
        console.log('[Live2D EVENT RECEIVED]', {
          expression: data.expression,
          motion: data.motion,
          speaking: data.speaking,
        })
        eventBus.emit('runtime:character_state', {
          activity: data.speaking ? 'speaking' : 'idle',
          emotion: data.emotion,
          intensity: data.intensity,
          expression: data.expression,
          motion: data.motion,
          behavior: data.behavior,
          attention: data.attention,
          energy: data.energy,
          durationMs: data.duration_ms,
        })
        eventBus.emit('runtime:character_intent', {
          emotion: data.emotion, behavior: data.behavior || data.motion, attention: data.attention || 'user',
          energy: data.energy ?? data.intensity, intensity: data.intensity, durationMs: data.duration_ms,
        })
        break

      // Legacy wire compatibility only. Runtime presentation is V2
      // character_update/character_state and must not create a second path.
      case 'character_action':
        console.warn('[Live2D] Ignoring legacy character_action; expected V2 character_update')
        break

      // User message (ASR transcription forwarded from voice input)
      case 'user_message':
        eventBus.emit('runtime:user_message', { text: data.text })
        break

      // Command response
      case 'command_response':
        eventBus.emit('runtime:command_response', {
          action: data.action,
          data: data.data,
        })
        break

      case 'tool_confirmation': {
        const approved = window.confirm(
          `AI 请求调用工具“${data.tool}”\n风险级别：${data.risk}\n参数：${JSON.stringify(data.args, null, 2)}`
        )
        void fetch(`/api/tool-confirmations/${encodeURIComponent(data.request_id)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved }),
        })
        break
      }

      // Errors
      case 'error':
        eventBus.emit('runtime:error', { code: data.code, message: data.message })
        break

      // Avatar control messages
      case 'avatar_component':
        eventBus.emit('avatar:component_update', {
          name: data.name,
          displayName: data.display_name,
          enabled: data.enabled,
          controller: data.controller,
          priority: data.priority,
          expression: data.expression,
          paramIds: data.param_ids,
        })
        break

      case 'avatar_expression':
        eventBus.emit('avatar:expression_update', {
          name: data.name,
          intensity: data.intensity,
          controller: data.controller,
          priority: data.priority,
        })
        break

      case 'avatar_motion':
        eventBus.emit('avatar:motion_update', {
          name: data.name,
          controller: data.controller,
          priority: data.priority,
          loop: data.loop,
        })
        break

      case 'avatar_state':
        eventBus.emit('avatar:state_restored', {
          components: data.components,
          expression: data.expression,
          intensity: data.expression_intensity,
          motion: data.motion,
        })
        break

      case 'avatar_suggestion':
        eventBus.emit('avatar:suggestion', {
          target: data.target,
          name: data.name,
          action: data.action,
          reason: data.reason,
          suggestionId: data.suggestion_id,
        })
        break

      // Keepalive
      case 'ping':
        this.send({ type: 'ping' })
        break
      case 'pong':
        this.pongPending = false
        break
    }
  }

  private startPing(): void {
    this.stopPing()
    this.pongPending = false
    this.pingTimer = setInterval(() => {
      if (this.pongPending) {
        this.ws?.close()
        return
      }
      this.pongPending = true
      this.send({ type: 'ping' })
    }, 30000)
  }

  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
    this.pongPending = false
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    if (this.reconnectAttempts >= this.reconnectMaxAttempts) {
      eventBus.emit('runtime:error', { code: 'MAX_RECONNECT', message: 'Max reconnect attempts reached' })
      return
    }
    const delay = Math.min(this.reconnectBaseDelay * Math.pow(2, this.reconnectAttempts), this.reconnectMaxDelay)
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }
}
