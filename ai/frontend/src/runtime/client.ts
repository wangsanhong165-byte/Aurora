// WebSocket Client — connects to Companion Runtime via V2/V3 Transport Protocol

import { eventBus } from '../core/event-bus'
import type { OutboundMessage } from './protocol'
import { validateVersion, SequenceTracker } from './envelope'
import { v2ToV3Envelope, type TransitionalEnvelope } from './compat'

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
  private sessionId = ''
  private sequenceTracker = new SequenceTracker()
  private sequenceCounter = 0

  constructor(url: string) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return
    this.intentionalClose = false

    // Listen for avatar send requests from AvatarController
    if (!this._unsubAvatarSend) {
      this._unsubAvatarSend = eventBus.on('avatar:send', (data) => {
        this.sendViaEnvelope(data as Record<string, unknown>)
      })
    }

    eventBus.emit('connection:change', { connected: false })

    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this.sequenceTracker.reset()
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
        const raw = JSON.parse(event.data) as Record<string, unknown>

        // Canonical V3 envelope or transitional V2 flat frame.
        if ('protocolVersion' in raw) {
          this.dispatchV3Envelope(raw)
        } else {
          const envelope = v2ToV3Envelope(raw, this.sessionId)
          this.dispatchV3Payload(envelope.eventType, envelope.payload, envelope.turnId ?? '')
        }
      } catch (err) {
        console.warn('[WS] Malformed message:', err)
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
      // Wrap in V3 envelope with V2-type content for backward compat
      this.sendViaEnvelope(msg as unknown as Record<string, unknown>)
    }
  }

  private sendViaEnvelope(data: Record<string, unknown>): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return
    this.sequenceCounter++
    const envelope: TransitionalEnvelope = {
      protocolVersion: '3.0',
      eventId: `evt_${crypto.randomUUID()}`,
      eventType: String(data.type ?? ''),
      sessionId: this.sessionId,
      turnId: null,
      sequence: this.sequenceCounter,
      timestamp: Date.now() / 1000,
      source: 'frontend',
      payload: data,
    }
    this.ws.send(JSON.stringify(envelope))
  }

  sendText(text: string): void {
    this.send({ type: 'text_input', text } as unknown as OutboundMessage)
  }

  sendInterrupt(): void {
    this.send({ type: 'interrupt' } as unknown as OutboundMessage)
  }

  sendCommand(action: string, params: Record<string, unknown> = {}, requestId?: string): void {
    this.send({ type: 'command', action, params, request_id: requestId } as unknown as OutboundMessage)
  }

  sendAudioSamples(samples: Float32Array, sampleRate: number): void {
    this.send({ type: 'audio_input', samples: Array.from(samples), sample_rate: sampleRate } as unknown as OutboundMessage)
  }

  sendAudioEnd(): void {
    this.send({ type: 'audio_end' } as unknown as OutboundMessage)
  }

  // ── V3 envelope dispatch ──

  private dispatchV3Envelope(raw: Record<string, unknown>): void {
    try {
      const envelope = raw as unknown as TransitionalEnvelope

      // Validate protocol version
      try {
        validateVersion(envelope.protocolVersion)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'unsupported version'
        console.warn('[WS] Unsupported protocol version:', envelope.protocolVersion)
        eventBus.emit('runtime:error', { code: 'unsupported_protocol_version', message: msg })
        return
      }

      // Update session ID from server
      if (envelope.sessionId && !this.sessionId) {
        this.sessionId = envelope.sessionId
      }

      // Check sequence (out-of-order / duplicate detection)
      if (envelope.eventType !== 'session.opened' && envelope.eventType !== 'session.pong') {
        if (!this.sequenceTracker.accept(envelope.sessionId, envelope.sequence)) {
          console.warn('[WS] Duplicate or out-of-order message:', envelope.eventType, envelope.sequence)
          return
        }
      }

      // Dispatch by type
      this.dispatchV3Payload(envelope.eventType, envelope.payload, envelope.turnId ?? '')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'parse error'
      console.warn('[WS] Envelope error:', msg)
      eventBus.emit('runtime:error', { code: 'envelope_parse_error', message: msg })
    }
  }

  private dispatchV3Payload(type: string, payload: Record<string, unknown>, _turnId: string = ''): void {
    switch (type) {
      // ── V3 event types ──
      case 'runtime.status':
        eventBus.emit('runtime:status', {
          status: payload.state as string,
          message: payload.message as string,
        })
        if (payload.state === 'speaking') {
          eventBus.emit('character:activity', { activity: 'speaking' })
        } else if (payload.state === 'processing') {
          eventBus.emit('character:activity', { activity: 'thinking' })
        }
        break

      case 'assistant.text.started':
        break

      case 'assistant.text.completed':
        eventBus.emit('runtime:message', {
          text: payload.text as string,
          reasoning: payload.reasoning as string | undefined,
        })
        break

      case 'tts.started':
        eventBus.emit('runtime:tts_start', {
          format: (payload.format as string) || 'wav',
          sequence: (payload.audioSequence as number) || 0,
        })
        eventBus.emit('character:activity', { activity: 'speaking' })
        break

      case 'tts.audio':
        eventBus.emit('audio:play', {
          audio: payload.data as string,
          format: (payload.format as string) || 'wav',
          volumeArray: payload.volumes as number[] | undefined,
        })
        break

      case 'tts.completed':
        eventBus.emit('runtime:tts_end', { reason: (payload.reason as string) || 'complete' })
        break

      case 'character.intent':
        eventBus.emit('runtime:character_intent', {
          emotion: payload.emotion as string,
          behavior: (payload.behavior as string) || 'speak',
          attention: (payload.attention as string) || 'user',
          energy: (payload.energy ?? payload.intensity) as number,
          intensity: (payload.intensity as number) ?? 0.5,
          durationMs: payload.durationMs as number | undefined,
          naturalVAD: payload.naturalVAD as { valence: number; arousal: number; dominance: number } | undefined,
          contextTags: payload.contextTags as string[] | undefined,
        })
        break

      case 'user.text':
        eventBus.emit('runtime:user_message', { text: payload.text as string })
        break

      case 'session.opened':
        eventBus.emit('connection:change', { connected: true })
        break

      // ── Legacy V2 event types (compatibility) ──
      case 'session':
        if (payload.status === 'init') {
          eventBus.emit('connection:change', { connected: true })
        }
        break

      case 'runtime_status':
        eventBus.emit('runtime:status', {
          status: payload.state as string,
          message: payload.message as string,
        })
        if (payload.state === 'speaking') {
          eventBus.emit('character:activity', { activity: 'speaking' })
        } else if (payload.state === 'processing') {
          eventBus.emit('character:activity', { activity: 'thinking' })
        }
        break

      case 'assistant_message':
        eventBus.emit('runtime:message', {
          text: payload.text as string,
          reasoning: payload.reasoning as string | undefined,
          segments: payload.segments as Array<{ text: string; emotion: string; behavior: string }> | undefined,
          diagnostics: payload.diagnostics as Record<string, unknown> | undefined,
        })
        break

      case 'assistant_chunk':
        eventBus.emit('runtime:chunk', {
          text: payload.text as string,
          delta: payload.delta as string,
        })
        break

      case 'user_message':
        eventBus.emit('runtime:user_message', { text: payload.text as string })
        break

      case 'tts_start':
        eventBus.emit('runtime:tts_start', {
          format: payload.format as string,
          sequence: payload.sequence as number,
        })
        eventBus.emit('character:activity', { activity: 'speaking' })
        break

      case 'tts_audio':
        eventBus.emit('audio:play', {
          audio: payload.data as string,
          format: payload.format as string,
          volumeArray: payload.volumes as number[] | undefined,
        })
        break

      case 'tts_end':
        eventBus.emit('runtime:tts_end', { reason: payload.reason as string })
        break

      case 'character_update':
        console.log('[Live2D EVENT RECEIVED]', {
          emotion: payload.emotion,
          behavior: payload.behavior,
          speaking: payload.speaking,
        })
        eventBus.emit('runtime:character_intent', {
          emotion: payload.emotion as string,
          behavior: (payload.behavior as string) || 'speak',
          attention: (payload.attention as string) || 'user',
          energy: (payload.energy ?? payload.intensity) as number,
          intensity: payload.intensity as number,
          durationMs: payload.duration_ms as number | undefined,
          naturalVAD: payload.natural_vad as { valence: number; arousal: number; dominance: number } | undefined,
          contextTags: payload.context_tags as string[] | undefined,
        })
        break

      case 'command_response':
        eventBus.emit('runtime:command_response', {
          action: payload.action as string,
          data: payload.data as Record<string, unknown>,
          requestId: payload.request_id as string,
        })
        break

      case 'tool_confirmation':
        eventBus.emit('runtime:permission_requested', {
          requestId: payload.request_id as string,
          capability: payload.tool as string,
          args: payload.args as Record<string, unknown>,
          risk: payload.risk as string,
        })
        break

      case 'error':
        eventBus.emit('runtime:error', {
          code: payload.code as string,
          message: payload.message as string,
          requestId: payload.request_id as string,
        })
        break

      case 'telemetry':
        // Optional: forward telemetry events to debug panel
        eventBus.emit('runtime:telemetry', payload as { events: Array<Record<string, unknown>> })
        break

      // Avatar control
      case 'avatar_component':
        eventBus.emit('avatar:component_update', {
          name: payload.name as string,
          displayName: payload.display_name as string,
          enabled: payload.enabled as boolean,
          controller: payload.controller as string,
          priority: payload.priority as number,
          expression: payload.expression as string,
          paramIds: payload.param_ids as string[],
        })
        break

      case 'avatar_expression':
        eventBus.emit('avatar:expression_update', {
          name: payload.name as string,
          intensity: payload.intensity as number,
          controller: payload.controller as string,
          priority: payload.priority as number,
        })
        break

      case 'avatar_motion':
        eventBus.emit('avatar:motion_update', {
          name: payload.name as string,
          controller: payload.controller as string,
          priority: payload.priority as number,
          loop: payload.loop as boolean,
        })
        break

      case 'avatar_state':
        eventBus.emit('avatar:state_restored', {
          components: payload.components as Record<string, boolean>,
          expression: payload.expression as string,
          intensity: payload.expression_intensity as number,
          motion: payload.motion as string,
        })
        break

      case 'avatar_suggestion':
        eventBus.emit('avatar:suggestion', {
          target: payload.target as string,
          name: payload.name as string,
          action: payload.action as string,
          reason: payload.reason as string,
          suggestionId: payload.suggestion_id as string,
        })
        break

      // Keepalive
      case 'session.ping':
        this.sendViaEnvelope({ type: 'session.pong', nonce: payload.nonce ?? '' })
        break

      case 'session.pong':
        this.pongPending = false
        break

      default:
        // Unknown event — report instead of silent ignore
        console.warn('[WS] Unhandled event type:', type)
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
      this.sendViaEnvelope({ type: 'session.ping', nonce: '' })
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
