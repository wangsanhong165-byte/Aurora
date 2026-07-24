// Status bar — connection, AI state, TTS status

import { useSelector, selectConnection, selectActivity, selectStatusMessage, selectCharacter, selectAudioState } from '../core/store'
import type { ConnectionState, AiActivity } from '../core/types'

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  disconnected: 'Offline',
  connecting: 'Connecting...',
  connected: 'Connected',
}

const CONNECTION_COLOR: Record<ConnectionState, string> = {
  disconnected: '#e74c3c',
  connecting: '#f39c12',
  connected: '#4caf50',
}

const ACTIVITY_LABEL: Record<AiActivity, string> = {
  idle: 'Idle',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  processing: 'Processing',
}

const ACTIVITY_COLOR: Record<AiActivity, string> = {
  idle: '#888',
  listening: '#42a5f5',
  thinking: '#ffd700',
  speaking: '#4caf50',
  processing: '#f39c12',
}

function PulseDot({ color }: { color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
        animation: 'pulse 2s ease-in-out infinite',
      }}
    />
  )
}

export function StatusBar() {
  const connection = useSelector(selectConnection)
  const activity = useSelector(selectActivity)
  const statusMessage = useSelector(selectStatusMessage)
  const character = useSelector(selectCharacter)
  const audio = useSelector(selectAudioState)

  return (
    <div style={styles.bar}>
      {/* Left: Connection */}
      <div style={styles.section}>
        <PulseDot color={CONNECTION_COLOR[connection]} />
        <span style={styles.label}>{CONNECTION_LABEL[connection]}</span>
      </div>

      {/* Center: Status message */}
      <div style={styles.center}>
        {statusMessage && (
          <span style={styles.statusText}>{statusMessage}</span>
        )}
      </div>

      {/* Right: AI state */}
      <div style={styles.section}>
        <span style={styles.emotionTag}>{character.emotion}</span>
        <PulseDot color={ACTIVITY_COLOR[activity]} />
        <span style={styles.label}>{ACTIVITY_LABEL[activity]}</span>
        {audio.isPlaying && <span style={styles.ttsIndicator}>🔊</span>}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 1rem',
    height: 32,
    backgroundColor: '#141418',
    borderBottom: '1px solid #2a2a2e',
    fontSize: '0.78rem',
    color: '#888',
    fontFamily: 'monospace',
    flexShrink: 0,
    gap: 12,
  },
  section: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    minWidth: 140,
  },
  center: {
    flex: 1,
    textAlign: 'center',
    overflow: 'hidden',
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
  },
  label: {
    color: '#aaa',
  },
  statusText: {
    color: '#777',
    fontStyle: 'italic',
    fontSize: '0.72rem',
  },
  emotionTag: {
    color: '#e0c080',
    fontWeight: 500,
    textTransform: 'uppercase',
    fontSize: '0.7rem',
    letterSpacing: '0.05em',
    backgroundColor: 'rgba(224, 192, 128, 0.1)',
    padding: '2px 6px',
    borderRadius: 4,
  },
  ttsIndicator: {
    fontSize: '0.7rem',
  },
}
