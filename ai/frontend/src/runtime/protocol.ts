// Runtime Protocol V2 — formal message types between Frontend and Runtime
// Mirrors app/transport/protocol.py

// ── Inbound: Runtime → Frontend ──

export interface AssistantMessage {
  type: 'assistant_message'
  text: string
  reasoning?: string
  segments?: Array<{ text: string; emotion: string; behavior: string }>
  diagnostics?: {
    llm_usage?: {
      prompt_tokens?: number
      completion_tokens?: number
      total_tokens?: number
      cached_tokens?: number
      model?: string
      estimated_cost_usd?: number
    }
    context_budget?: Record<string, unknown>
    retrieved_memories?: Array<Record<string, unknown>>
    learned_memories?: Array<Record<string, unknown>>
  }
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

export interface ToolConfirmation {
  type: 'tool_confirmation'
  request_id: string
  tool: string
  args: Record<string, unknown>
  risk: string
}

/** Renderer-independent semantic presentation update from Runtime V3. */
export interface CharacterUpdate {
  type: 'character_update'
  emotion: string      // semantic emotion (e.g. "happy")
  intensity: number     // 0-1
  speaking: boolean
  timestamp: number
  behavior?: string
  attention?: 'user' | 'screen' | 'away' | 'neutral'
  energy?: number
  duration_ms?: number
  natural_vad?: { valence: number; arousal: number; dominance: number }
  context_tags?: string[]
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
  request_id?: string
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
  request_id?: string
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
  | CharacterUpdate
  | SessionEvent
  | Error
  | Pong
  | ServerPing
  | UserMessage
  | CommandResponse
  | ToolConfirmation
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
  request_id?: string
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
