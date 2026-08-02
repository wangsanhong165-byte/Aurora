import { LoaderCircle, MessageSquare, Plus, X } from 'lucide-react'

export interface HistoryEntry {
  uid: string
  latest_message: string
  timestamp: string
}

export interface HistoryPanelProps {
  histories: HistoryEntry[]
  activeUid: string
  loading: boolean
  onLoad: (uid: string) => void
  onDelete: (uid: string) => void
  onCreate: () => void
}

function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) return iso
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins} 分钟前`
    if (diffHours < 24) return `${diffHours} 小时前`
    if (diffDays < 7) return `${diffDays} 天前`

    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return iso
  }
}

function truncate(text: unknown, maxLen: number): string {
  if (typeof text !== 'string') return String(text ?? '')
  if (text.length <= maxLen) return text
  return `${text.slice(0, maxLen).trimEnd()}...`
}

export function HistoryPanel({
  histories,
  activeUid,
  loading,
  onLoad,
  onDelete,
  onCreate,
}: HistoryPanelProps) {
  return (
    <div className="history-panel">
      <div className="history-header">
        <button
          type="button"
          className="history-new-button"
          onClick={onCreate}
          title="新建会话"
          aria-label="新建会话"
        >
          <Plus size={16} strokeWidth={1.75} aria-hidden="true" />
          <span>新建会话</span>
        </button>
      </div>

      <div className="history-list">
        {loading && histories.length === 0 && (
          <div className="history-center-state">
            <LoaderCircle className="history-spinner" size={20} strokeWidth={1.75} aria-hidden="true" />
            <span className="history-state-text">正在加载…</span>
          </div>
        )}

        {!loading && histories.length === 0 && (
          <div className="history-center-state">
            <MessageSquare className="history-state-icon" size={24} strokeWidth={1.75} aria-hidden="true" />
            <span className="history-state-text">还没有聊天记录</span>
            <span className="history-state-hint">
              开始聊天后，会话会出现在这里。
            </span>
          </div>
        )}

        {histories.map((entry) => {
          const isActive = entry.uid === activeUid

          const handleDelete = (event: React.MouseEvent) => {
            event.stopPropagation()
            onDelete(entry.uid)
          }

          return (
            <div
              key={entry.uid}
              role="button"
              tabIndex={0}
              className={`history-item${isActive ? ' is-active' : ''}`}
              onClick={() => onLoad(entry.uid)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onLoad(entry.uid)
                }
              }}
            >
              <div className="history-item-content">
                <div className="history-item-snippet">
                  {entry.latest_message
                    ? truncate(entry.latest_message, 60)
                    : '空白会话'}
                </div>
                <div className="history-item-meta">
                  <span className="history-item-timestamp">
                    {formatTimestamp(entry.timestamp)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="history-delete-button"
                onClick={handleDelete}
                title="删除会话"
                aria-label="删除会话"
              >
                <X size={15} strokeWidth={1.75} aria-hidden="true" />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
