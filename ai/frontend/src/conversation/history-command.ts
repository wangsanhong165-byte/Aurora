export interface HistoryCommandEffect {
  activeUid: string
  clearMessages: boolean
  messages: unknown[] | null
  refreshHistories: boolean
}

export function resolveHistoryCommand(
  action: string,
  data: Record<string, unknown>,
): HistoryCommandEffect | null {
  if (action === 'load_history') {
    return {
      activeUid: String(data.history_uid ?? ''),
      clearMessages: false,
      messages: Array.isArray(data.messages) ? data.messages : [],
      refreshHistories: false,
    }
  }
  if (action === 'create_history') {
    return {
      activeUid: String(data.history_uid ?? ''),
      clearMessages: true,
      messages: null,
      refreshHistories: true,
    }
  }
  return null
}
