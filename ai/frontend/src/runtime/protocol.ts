// Runtime Protocol V2 — formal message types between Frontend and Runtime
// Mirrors app/transport/protocol.py

// ── Inbound: Runtime → Frontend ──

export interface AssistantMessage {
  type: 'assistant_message'
  text: string
  reasoning?: string
  segments?: Array<{ text: string; tone: string; gesture: string }>
}

export interface AssistantChunk {
  type: 'assistant_chunk'
  text: string
  delta: string
}

export interface TtsStart {
  type: 'tts_start'
  format: string
  sequence: number
}

export interface TtsAudio {
  type: 'tts_audio'
  data: string // base64-encoded WAV
  format: string
  sequence: number
  volumes?: number[] // RMS per 20ms chunk for lip-sync
}

export interface TtsEnd {
  type: 'tts_end'
  reason: 'complete' | 'interrupted' | 'error'
}

export interface RuntimeStatus {
  type: 'runtime_status'
  state: string // "processing" | "speaking" | "idle" | "error"
  message: string
}

export interface CharacterAction {
  type: 'character_action'
  emotion: string
  intensity: number
  gesture: string
}

export interface CharacterState {
  type: 'character_state'
  activity: string    // "idle" | "thinking" | "speaking" | "listening"
  emotion: string     // emotion name
  intensity: number   // emotion intensity 0-1
  expression: string  // specific expression name
  motion: string      // gesture/motion name
  behavior?: string
  attention?: 'user' | 'screen' | 'away' | 'neutral'
  energy?: number
  duration_ms?: number
}

/** Model-ready Live2D presentation update from V2 Runtime */
export interface CharacterUpdate {
  type: 'character_update'
  model_id: string
  emotion: string      // semantic emotion (e.g. "happy")
  intensity: number     // 0-1
  expression: string    // model-specific expression name (e.g. "zs1")
  motion: string        // gesture/motion name
  speaking: boolean
  timestamp: number
  behavior?: string
  attention?: 'user' | 'screen' | 'away' | 'neutral'
  energy?: number
  duration_ms?: number
}

export interface SessionEvent {
  type: 'session'
  status: string // "init" | "connected" | "disconnected"
  config: Record<string, unknown>
}

export interface Error {
  type: 'error'
  code: string
  message: string
}

export interface Pong {
  type: 'pong'
}

export interface ServerPing {
  type: 'ping'
}

export interface UserMessage {
  type: 'user_message'
  text: string
}

export interface CommandResponse {
  type: 'command_response'
  action: string
  data: Record<string, unknown>
}

// ── Avatar Protocol: Server → Frontend ──

export interface AvatarComponentUpdate {
  type: 'avatar_component'
  name: string           // config key: "goggles"
  display_name: string   // "护目镜"
  enabled: boolean
  controller: string     // "USER" | "AI" | "SYSTEM"
  priority: number
  expression: string     // .exp3.json file name
  param_ids: string[]
}

export interface AvatarExpressionUpdate {
  type: 'avatar_expression'
  name: string           // semantic: "happy"
  intensity: number
  controller: string
  priority: number
}

export interface AvatarMotionUpdate {
  type: 'avatar_motion'
  name: string           // "wave"
  controller: string
  priority: number
  loop: boolean
}

export interface AvatarStateSnapshot {
  type: 'avatar_state'
  components: Record<string, boolean>
  expression: string
  expression_intensity: number
  motion: string
  model_id: string
}

export interface AvatarSuggestion {
  type: 'avatar_suggestion'
  target: string         // "component" | "expression" | "motion"
  name: string
  action: string         // "enable" | "disable" | "toggle"
  reason: string
  suggestion_id: string
}

export type InboundMessage =
  | AssistantMessage
  | AssistantChunk
  | TtsStart
  | TtsAudio
  | TtsEnd
  | RuntimeStatus
  | CharacterAction
  | CharacterState
  | CharacterUpdate
  | SessionEvent
  | Error
  | Pong
  | ServerPing
  | UserMessage
  | CommandResponse
  // Avatar protocol
  | AvatarComponentUpdate
  | AvatarExpressionUpdate
  | AvatarMotionUpdate
  | AvatarStateSnapshot
  | AvatarSuggestion

// ── Outbound: Frontend → Runtime ──

export interface TextInput {
  type: 'text_input'
  text: string
}

export interface AudioInput {
  type: 'audio_input'
  samples: number[]
  sample_rate: number
}

export interface AudioEnd {
  type: 'audio_end'
}

export interface Interrupt {
  type: 'interrupt'
}

export interface Ping {
  type: 'ping'
}

export interface Command {
  type: 'command'
  action: string
  params: Record<string, unknown>
}

// ── Avatar Protocol: Frontend → Server ──

export interface AvatarRequest {
  type: 'avatar_request'
  target: string         // "component" | "expression" | "motion"
  name: string           // "glasses" | "happy" | "wave"
  action: string         // "enable" | "disable" | "toggle"
  source: string         // "user" | "ai"
  priority: number       // 100 for user, 50 for ai
}

export interface AvatarAccept {
  type: 'avatar_accept'
  suggestion_id: string
}

export interface AvatarReject {
  type: 'avatar_reject'
  suggestion_id: string
}

export type OutboundMessage =
  | TextInput
  | AudioInput
  | AudioEnd
  | Interrupt
  | Ping
  | Command
  | AvatarRequest
  | AvatarAccept
  | AvatarReject
