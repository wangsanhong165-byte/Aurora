// Runtime Adapter — provides typed API for frontend → runtime communication
// Wraps RuntimeClient and provides lifecycle management + typed send methods.
// All inbound messages flow: WebSocket → RuntimeClient → EventBus → Components
// Components must never handle WebSocket messages directly.

import { RuntimeClient } from './client'
import type { OutboundMessage } from './protocol'

export class RuntimeAdapter {
  private client: RuntimeClient
  private _connected = false

  constructor(url: string) {
    this.client = new RuntimeClient(url)
  }

  /** Whether the WebSocket is currently connected */
  get connected(): boolean {
    return this._connected
  }

  /** Start connection */
  connect(): void {
    this.client.connect()
    // Poll connection state (RuntimeClient emits events but doesn't expose state)
    this._connected = false
  }

  /** Disconnect and clean up */
  disconnect(): void {
    this.client.disconnect()
    this._connected = false
  }

  /** Send text input */
  sendText(text: string): void {
    this.client.sendText(text)
  }

  /** Send interrupt signal */
  sendInterrupt(): void {
    this.client.sendInterrupt()
  }

  /** Send audio samples from microphone */
  sendAudioSamples(samples: Float32Array, sampleRate: number): void {
    this.client.sendAudioSamples(samples, sampleRate)
  }

  /** Signal end of audio input */
  sendAudioEnd(): void {
    this.client.sendAudioEnd()
  }

  /** Send a management command */
  sendCommand(action: string, params: Record<string, unknown> = {}): void {
    this.client.sendCommand(action, params)
  }

  /** Send arbitrary outbound message */
  send(msg: OutboundMessage): void {
    this.client.send(msg)
  }
}
