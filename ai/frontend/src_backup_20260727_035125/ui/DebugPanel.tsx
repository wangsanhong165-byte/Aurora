// Developer Diagnostics Panel — runtime observability overlay
// Toggle with Ctrl+Shift+D or click the status bar corner
// Shows: WS protocol, connected services, runtime state, model info, expression, audio

import { useState, useEffect, useRef } from 'react'
import { eventBus } from '../core/event-bus'

interface DiagState {
  connected: boolean
  wsProtocol: string
  runtimeState: string
  runtimeMessage: string
  currentModel: string
  lastExpression: string
  lastMotion: string
  lastLive2dEvent: string
  ttsState: string
  audioQueueLen: number
  sessionConfig: Record<string, unknown>
  lastError: string
  performance: string
  bindings: string
  intent: string
  performanceDebug: string
  llmDiagnostics: string
}

export function DebugPanel() {
  const [visible, setVisible] = useState(false)
  const [parameterGain, setParameterGain] = useState(1.45)
  const [bodyMotionGain, setBodyMotionGain] = useState(1.25)
  const [nativeMotions, setNativeMotions] = useState<string[]>([])
  const [nativeExpressions, setNativeExpressions] = useState<string[]>([])
  const [state, setState] = useState<DiagState>({
    connected: false,
    wsProtocol: '—',
    runtimeState: '—',
    runtimeMessage: '',
    currentModel: '—',
    lastExpression: '—',
    lastMotion: '—',
    lastLive2dEvent: '—',
    ttsState: '—',
    audioQueueLen: 0,
    sessionConfig: {},
    lastError: '',
    performance: 'none',
    bindings: 'none',
    intent: 'none',
    performanceDebug: 'none',
    llmDiagnostics: 'none',
  })
  const stateRef = useRef(state)
  stateRef.current = state

  useEffect(() => {
    const unsubs: (() => void)[] = []

    unsubs.push(eventBus.on('connection:change', ({ connected }) => {
      setState(s => ({ ...s, connected, wsProtocol: connected ? '/client-ws' : '—' }))
    }))

    unsubs.push(eventBus.on('runtime:status', ({ status, message }) => {
      setState(s => ({ ...s, runtimeState: status, runtimeMessage: message || '' }))
    }))

    unsubs.push(eventBus.on('runtime:session', ({ config }) => {
      setState(s => ({ ...s, sessionConfig: config }))
    }))

    unsubs.push(eventBus.on('runtime:character_state', ({ expression, motion, emotion }) => {
      const now = new Date().toLocaleTimeString()
      setState(s => ({
        ...s,
        lastExpression: expression || emotion || '—',
        lastMotion: motion || '—',
        lastLive2dEvent: now + ` (expr=${expression || emotion}, motion=${motion || 'none'})`,
      }))
    }))

    unsubs.push(eventBus.on('runtime:tts_start', () => {
      setState(s => ({ ...s, ttsState: 'playing', audioQueueLen: s.audioQueueLen + 1 }))
    }))

    unsubs.push(eventBus.on('runtime:tts_end', () => {
      setState(s => ({ ...s, ttsState: 'idle', audioQueueLen: Math.max(0, s.audioQueueLen - 1) }))
    }))

    unsubs.push(eventBus.on('runtime:error', ({ message }) => {
      setState(s => ({ ...s, lastError: message }))
    }))

    unsubs.push(eventBus.on('character:performance', (performance) => {
      setState(s => ({ ...s, performance: JSON.stringify(performance) }))
    }))

    unsubs.push(eventBus.on('character:performance_debug', (debug) => {
      setState(s => ({ ...s, performanceDebug: JSON.stringify(debug, null, 2) }))
    }))

    unsubs.push(eventBus.on('runtime:character_intent', (intent) => {
      setState(s => ({ ...s, intent: JSON.stringify(intent) }))
    }))

    unsubs.push(eventBus.on('runtime:message', ({ diagnostics }) => {
      if (diagnostics) {
        setState(s => ({ ...s, llmDiagnostics: JSON.stringify(diagnostics, null, 2) }))
      }
    }))

    unsubs.push(eventBus.on('character:native_catalog', ({ motions, expressions }) => {
      setNativeMotions(motions)
      setNativeExpressions(expressions)
    }))

    // Read model from global
    try {
      const init = (window as any).__INITIAL_MODEL_INFO__
      if (init?.name) {
        const bindings = init.avatarProfiles?.[init.name]?.bindings ?? {}
        setState(s => ({ ...s, currentModel: init.name, bindings: JSON.stringify(bindings) }))
      }
    } catch (_) {}

    // Keyboard shortcut
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        setVisible(v => !v)
      }
    }
    window.addEventListener('keydown', onKey)

    return () => {
      unsubs.forEach(fn => fn())
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  if (!visible) return null

  const setPerformanceMode = (mode: 'legacy' | 'enhanced' | 'calibration') => {
    eventBus.emit('character:performance_tuning', { mode })
  }

  const rows: [string, string][] = [
    ['WS Connected', state.connected ? '● YES' : '○ NO'],
    ['WS Protocol', state.wsProtocol],
    ['Runtime', `${state.runtimeState}${state.runtimeMessage ? ' / ' + state.runtimeMessage : ''}`],
    ['Model', state.currentModel],
    ['Expression', state.lastExpression],
    ['Motion', state.lastMotion],
    ['Performance', state.performance],
    ['Performance Runtime', state.performanceDebug],
    ['Character Intent', state.intent],
    ['Memory / Token', state.llmDiagnostics],
    ['Avatar Bindings', state.bindings],
    ['Last Live2D Event', state.lastLive2dEvent],
    ['TTS', state.ttsState],
    ['Audio Queue', String(state.audioQueueLen)],
    ['Session', JSON.stringify(state.sessionConfig).slice(0, 80) || '—'],
    ['Last Error', state.lastError || '—'],
  ]

  return (
    <div style={styles.backdrop} onClick={() => setVisible(false)}>
      <div style={styles.panel} onClick={e => e.stopPropagation()}>
        <div style={styles.header}>
          <span>🔍 Dev Diagnostics</span>
          <span style={styles.hint}>Ctrl+Shift+D to toggle</span>
        </div>
        <div style={styles.tuning}>
          <span>Performance A/B</span>
          <button onClick={() => setPerformanceMode('legacy')}>Legacy</button>
          <button onClick={() => setPerformanceMode('enhanced')}>Enhanced</button>
          <button onClick={() => setPerformanceMode('calibration')}>Calibration</button>
          <button onClick={() => eventBus.emit('character:interaction', {
            type: 'touch', region: 'head', intensity: 0.8,
          })}>Test reaction</button>
          <label>
            Param {parameterGain.toFixed(2)}
            <input type="range" min="0.8" max="2.2" step="0.05" value={parameterGain}
              onChange={event => {
                const value = Number(event.target.value)
                setParameterGain(value)
                eventBus.emit('character:performance_tuning', { parameterGain: value })
              }} />
          </label>
          <label>
            Body {bodyMotionGain.toFixed(2)}
            <input type="range" min="0.6" max="2" step="0.05" value={bodyMotionGain}
              onChange={event => {
                const value = Number(event.target.value)
                setBodyMotionGain(value)
                eventBus.emit('character:performance_tuning', { bodyMotionGain: value })
              }} />
          </label>
          {(['happy', 'sad', 'angry', 'surprised', 'shy'] as const).map(emotion => (
            <button key={emotion} onClick={() => eventBus.emit('character:intent', {
              emotion, behavior: 'react', intensity: 0.85,
            })}>{emotion}</button>
          ))}
        </div>
        <div style={styles.catalog}>
          <span>Native motions</span>
          {nativeMotions.map(name => (
            <button key={name} onClick={() => eventBus.emit('character:native_preview', {
              type: 'motion', name,
            })}>{name}</button>
          ))}
          <span>Native expressions</span>
          {nativeExpressions.map(name => (
            <button key={name} onClick={() => eventBus.emit('character:native_preview', {
              type: 'expression', name,
            })}>{name}</button>
          ))}
        </div>
        <table style={styles.table}>
          <tbody>
            {rows.map(([label, value]) => (
              <tr key={label} style={styles.row}>
                <td style={styles.label}>{label}</td>
                <td style={styles.value}>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
    zIndex: 9999,
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'flex-end',
  },
  panel: {
    margin: '40px 20px 0 0',
    padding: '16px',
    backgroundColor: 'rgba(10,10,30,0.92)',
    border: '1px solid rgba(100,200,255,0.3)',
    borderRadius: '8px',
    fontFamily: 'monospace',
    fontSize: '12px',
    color: '#e0e0e0',
    minWidth: '380px',
    maxWidth: '500px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: '8px',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
    marginBottom: '8px',
    fontWeight: 600,
  },
  hint: {
    color: '#666',
    fontSize: '10px',
  },
  tuning: {
    display: 'flex',
    gap: 6,
    alignItems: 'center',
    flexWrap: 'wrap',
    margin: '8px 0 12px',
  },
  catalog: {
    display: 'flex',
    gap: 6,
    alignItems: 'center',
    flexWrap: 'wrap',
    marginBottom: 12,
    maxHeight: 110,
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  row: {
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  },
  label: {
    color: '#888',
    padding: '3px 8px 3px 0',
    whiteSpace: 'nowrap',
    verticalAlign: 'top',
  },
  value: {
    color: '#c0e0ff',
    padding: '3px 0',
    wordBreak: 'break-all',
    whiteSpace: 'pre-wrap',
  },
}
