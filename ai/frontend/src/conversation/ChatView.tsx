// Chat message panel

import { useRef, useEffect } from 'react'
import { useSelector, selectMessages } from '../core/store'
import type { ChatMessage } from '../core/types'

function Bubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  const isSystem = msg.role === 'system'

  const bubbleStyle: React.CSSProperties = {
    ...styles.bubble,
    alignSelf: isUser ? 'flex-end' : 'flex-start',
    backgroundColor: isUser ? '#2b5278' : '#222226',
    borderBottomRightRadius: isUser ? 4 : 14,
    borderBottomLeftRadius: isUser ? 14 : 4,
    opacity: isSystem ? 0.6 : 1,
    maxWidth: isUser ? '80%' : '90%',
  }

  return (
    <div style={bubbleStyle}>
      {!isUser && !isSystem && (
        <div style={styles.bubbleName}>Assistant</div>
      )}
      <div style={styles.bubbleText}>{msg.text}</div>
      {!isUser && !isSystem && msg.reasoning && (
        <details style={styles.reasoning}>
          <summary style={styles.reasoningSummary}>Thought process</summary>
          <div style={styles.reasoningText}>{msg.reasoning}</div>
        </details>
      )}
      <div style={styles.bubbleTime}>
        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  )
}

export function ChatView() {
  const messages = useSelector(selectMessages)
  const listRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive or last message text updates (streaming)
  const lastText = messages.length > 0 ? messages[messages.length - 1].text : ''
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages.length, lastText])

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        Conversation
        {messages.length > 0 && (
          <span style={styles.count}>{messages.length}</span>
        )}
      </div>
      <div ref={listRef} style={styles.list}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            Start a conversation with the character.
          </div>
        )}
        {messages.map((msg) => (
          <Bubble key={msg.id} msg={msg} />
        ))}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  header: {
    padding: '0.75rem 1rem',
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#999',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    borderBottom: '1px solid #2a2a2e',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flexShrink: 0,
  },
  count: {
    fontSize: '0.7rem',
    color: '#666',
    backgroundColor: '#222',
    padding: '1px 6px',
    borderRadius: 8,
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: '0.75rem',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  bubble: {
    padding: '0.5rem 0.75rem',
    borderRadius: 14,
  },
  bubbleName: {
    fontSize: '0.7rem',
    color: '#888',
    marginBottom: 4,
  },
  bubbleText: {
    color: '#ddd',
    fontSize: '0.85rem',
    lineHeight: 1.45,
    wordBreak: 'break-word',
    whiteSpace: 'pre-wrap',
  },
  reasoning: {
    marginTop: 8,
    borderTop: '1px solid #34343a',
    paddingTop: 6,
  },
  reasoningSummary: {
    color: '#8c8c96',
    cursor: 'pointer',
    fontSize: '0.72rem',
  },
  reasoningText: {
    color: '#a9a9b2',
    fontSize: '0.78rem',
    lineHeight: 1.4,
    whiteSpace: 'pre-wrap',
    marginTop: 6,
  },
  bubbleTime: {
    color: '#555',
    fontSize: '0.65rem',
    marginTop: 4,
    textAlign: 'right',
  },
  empty: {
    color: '#444',
    fontSize: '0.82rem',
    textAlign: 'center',
    padding: '2rem 1rem',
  },
}
