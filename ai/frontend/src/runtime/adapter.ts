// Runtime Adapter — provides typed API for frontend → runtime communication
// Wraps RuntimeClient and provides lifecycle management + typed send methods.
// All inbound messages flow: WebSocket → RuntimeClient → EventBus → Components
// Components must never handle WebSocket messages directly.

import { RuntimeClient } from './client'
import type { OutboundMessage } from './protocol'
import { eventBus } from '../core/event-bus'
import { CommandBroker } from '../session/command-broker'

export class RuntimeAdapter {
  private client: RuntimeClient
  private _connected = false
  private broker: CommandBroker
  private unsubscribers: Array<() => void>

  constructor(url: string) {
    this.client = new RuntimeClient(url)
    this.broker = new CommandBroker(message =>
      this.client.sendCommand(message.action, message.params, message.request_id))
    this.unsubscribers = [
      eventBus.on('runtime:command_response', event => {
        if (event.requestId) this.broker.resolve(event.requestId, event.data)
      }),
      eventBus.on('runtime:error', event => {
        if (event.requestId) this.broker.reject(event.requestId, new Error(`${event.code}: ${event.message}`))
      }),
      eventBus.on('connection:change', ({ connected }) => {
        this._connected = connected
        if (!connected) this.broker.dispose(new Error('runtime disconnected'))
      }),
    ]
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
    this.broker.dispose()
    this.unsubscribers.splice(0).forEach(unsubscribe => unsubscribe())
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

  requestCommand(action: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return this.broker.request(action, params)
  }

  /** Send arbitrary outbound message */
  send(msg: OutboundMessage): void {
    this.client.send(msg)
  }
}
