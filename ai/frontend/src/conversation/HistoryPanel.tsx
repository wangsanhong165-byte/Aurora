// History panel — saved conversation history with load/delete/create operations

import { theme } from '../core/theme'

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
    if (isNaN(date.getTime())) return iso
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`

    return date.toLocaleDateString([], {
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
  return text.slice(0, maxLen).trimEnd() + '...'
}

function Spinner() {
  return (
    <div
      style={{
        width: 20,
        height: 20,
        border: '2px solid #333',
        borderTopColor: theme.colors.accent,
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
        flexShrink: 0,
      }}
    />
  )
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
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.headerTitle}>Conversations</span>
        <button
          type="button"
          style={styles.newBtn}
          onClick={onCreate}
          title="New conversation"
        >
          +
        </button>
      </div>

      <div style={styles.list}>
        {loading && histories.length === 0 && (
          <div style={styles.centerState}>
            <Spinner />
            <span style={styles.stateText}>Loading...</span>
          </div>
        )}

        {!loading && histories.length === 0 && (
          <div style={styles.centerState}>
            <span style={styles.stateIcon}>💬</span>
            <span style={styles.stateText}>No saved conversations</span>
            <span style={styles.stateHint}>
              Your conversations will appear here after you start chatting.
            </span>
          </div>
        )}

        {histories.map((entry) => {
          const isActive = entry.uid === activeUid

          const handleDelete = (e: React.MouseEvent) => {
            e.stopPropagation()
            onDelete(entry.uid)
          }

          return (
            <div
              key={entry.uid}
              role="button"
              tabIndex={0}
              style={{
                ...styles.item,
                backgroundColor: isActive
                  ? theme.colors.bg.surface
                  : 'transparent',
              }}
              onClick={() => onLoad(entry.uid)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onLoad(entry.uid)
                }
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = theme.colors.bg.hover
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = 'transparent'
                }
              }}
            >
              <div style={styles.itemContent}>
                <div style={styles.itemSnippet}>
                  {entry.latest_message
                    ? truncate(entry.latest_message, 60)
                    : '(empty conversation)'}
                </div>
                <div style={styles.itemMeta}>
                  <span style={styles.itemTimestamp}>
                    {formatTimestamp(entry.timestamp)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                style={styles.deleteBtn}
                onClick={handleDelete}
                title="Delete conversation"
              >
                &times;
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  header: {
    padding: `${theme.spacing.md}px ${theme.spacing.lg}px`,
    borderBottom: `1px solid ${theme.colors.border}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: theme.fontSize.sm,
    fontWeight: theme.fontWeight.semibold,
    color: theme.colors.text.secondary,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  newBtn: {
    width: 26,
    height: 26,
    borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`,
    backgroundColor: theme.colors.bg.surface,
    color: theme.colors.text.primary,
    fontSize: theme.fontSize.lg,
    fontWeight: theme.fontWeight.normal,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    lineHeight: 1,
    padding: 0,
    transition: `background-color ${theme.animation.fast}`,
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: `${theme.spacing.xs}px`,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  item: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: theme.spacing.sm,
    padding: `${theme.spacing.sm}px ${theme.spacing.md}px`,
    borderRadius: theme.radius.md,
    border: 'none',
    textAlign: 'left' as const,
    width: '100%',
    cursor: 'pointer',
    outline: 'none',
    transition: `background-color ${theme.animation.fast}`,
    boxSizing: 'border-box' as const,
  },
  itemContent: {
    flex: 1,
    minWidth: 0,
  },
  itemSnippet: {
    fontSize: theme.fontSize.sm,
    color: theme.colors.text.primary,
    lineHeight: 1.4,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  itemMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: theme.spacing.sm,
    marginTop: 4,
  },
  itemTimestamp: {
    fontSize: theme.fontSize.xs,
    color: theme.colors.text.muted,
  },
  deleteBtn: {
    width: 22,
    height: 22,
    borderRadius: theme.radius.sm,
    border: 'none',
    backgroundColor: 'transparent',
    color: theme.colors.text.muted,
    fontSize: theme.fontSize.lg,
    lineHeight: 1,
    cursor: 'pointer',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
    transition: `color ${theme.animation.fast}`,
  },
  centerState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing.sm,
    padding: `${theme.spacing.xl}px ${theme.spacing.lg}px`,
    textAlign: 'center' as const,
  },
  stateIcon: {
    fontSize: '1.5rem',
    opacity: 0.4,
  },
  stateText: {
    fontSize: theme.fontSize.sm,
    color: theme.colors.text.muted,
  },
  stateHint: {
    fontSize: theme.fontSize.xs,
    color: theme.colors.text.muted,
    opacity: 0.7,
    maxWidth: 200,
  },
}
