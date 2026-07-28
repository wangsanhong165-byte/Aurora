// Runtime Event types — unified event format for frontend character runtime
// All external inputs (WebSocket, mouse, Electron IPC) are converted to
// RuntimeEvents before reaching CharacterRuntime.
// CharacterRuntime must never directly reference WebSocket envelope types,
// Python class names, or legacy tone/gesture fields.

import type { CharacterActivity } from './CharacterStateMachine'

// ── Intent (semantic, no renderer-specific data) ──

export interface CharacterIntent {
  emotion: string
  behavior?: string
  attention?: 'user' | 'screen' | 'away' | 'neutral'
  energy?: number
  durationMs?: number
  naturalVAD?: { valence: number; arousal: number; dominance: number }
  contextTags?: string[]
}

// ── Discriminated union of all runtime events ──

export type CharacterRuntimeEvent =
  // Turn lifecycle
  | { type: 'turn.listening.started'; turnId: string }
  | { type: 'turn.thinking.started'; turnId: string }
  | { type: 'turn.speaking.started'; turnId: string }
  | { type: 'turn.completed'; turnId: string }
  | { type: 'turn.cancelled'; turnId: string }

  // Speech / audio
  | { type: 'speech.started'; turnId: string; audioId: string }
  | { type: 'speech.ended'; turnId: string; audioId: string; reason: 'complete' | 'interrupted' | 'error' }

  // Intent from backend
  | { type: 'intent.received'; turnId: string; intent: CharacterIntent }

  // User interaction
  | { type: 'interaction.pointer-moved'; x: number; y: number }
  | { type: 'interaction.model-clicked'; hitArea?: string }
  | { type: 'interaction.drag-started'; x: number; y: number }
  | { type: 'interaction.drag-moved'; x: number; y: number }
  | { type: 'interaction.drag-ended'; x: number; y: number }

  // Runtime control
  | { type: 'runtime.cancel-turn'; turnId: string }
  | { type: 'runtime.reset' }
  | { type: 'state.transition'; from: CharacterActivity; to: CharacterActivity }
