// Main layout — character area (center), chat (collapsible sidebar)

import { useState } from 'react'
import type { ReactNode } from 'react'

export interface LayoutProps {
  statusBar: ReactNode
  characterArea: ReactNode
  chatArea: ReactNode
  inputBar: ReactNode
}

export function Layout({ statusBar, characterArea, chatArea, inputBar }: LayoutProps) {
  const [chatOpen, setChatOpen] = useState(false)

  return (
    <div style={styles.root}>
      {statusBar}
      <div style={styles.main}>
        <div style={styles.characterArea}>
          {characterArea}
          {/* Chat toggle button — overlaid on character area */}
          <button
            type="button"
            onClick={() => setChatOpen(o => !o)}
            style={styles.chatToggle}
            title={chatOpen ? 'Hide chat' : 'Show chat'}
          >
            {chatOpen ? '▸' : '◂'}
          </button>
        </div>
        {chatOpen && (
          <div style={styles.chatPanel}>
            <div style={styles.chatHeader}>
              <span style={styles.chatTitle}>Conversation</span>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
                style={styles.chatCloseBtn}
              >
                ✕
              </button>
            </div>
            {chatArea}
          </div>
        )}
      </div>
      {inputBar}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#1a1a1e',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'row',
    overflow: 'hidden',
    minHeight: 0,
  },
  characterArea: {
    flex: 1,
    minWidth: 0,
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  chatToggle: {
    position: 'absolute',
    right: 8,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 28,
    height: 48,
    borderRadius: '6px 0 0 6px',
    border: '1px solid #2a2a2e',
    borderRight: 'none',
    backgroundColor: 'rgba(24, 24, 28, 0.7)',
    color: '#888',
    fontSize: '0.85rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
    transition: 'color 0.15s, background-color 0.15s',
  },
  chatPanel: {
    width: 360,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    borderLeft: '1px solid #2a2a2e',
    backgroundColor: '#18181c',
  },
  chatHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    borderBottom: '1px solid #2a2a2e',
    flexShrink: 0,
  },
  chatTitle: {
    fontSize: '0.85rem',
    fontWeight: 600,
    color: '#ccc',
    letterSpacing: '0.02em',
  },
  chatCloseBtn: {
    background: 'none',
    border: 'none',
    color: '#888',
    cursor: 'pointer',
    fontSize: '0.9rem',
    padding: '2px 4px',
  },
}
