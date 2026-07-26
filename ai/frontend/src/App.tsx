import { useEffect, useRef, useCallback, useState } from 'react'
import { StoreProvider, useActions, useSelector, selectSettings } from './core/store'
import { eventBus } from './core/event-bus'
import { RuntimeAdapter } from './runtime/adapter'
import { AudioPlayer } from './audio/player'
import { CharacterView } from './character/CharacterView'
import { ChatView } from './conversation/ChatView'
import { StatusBar } from './ui/StatusBar'
import { InputBar } from './ui/InputBar'
import { Layout, type WorkspaceSection } from './ui/Layout'
import { TitleBar } from './ui/TitleBar'
import { SettingsPanel } from './ui/SettingsPanel'
import { DebugPanel } from './ui/DebugPanel'
import { ErrorBoundary } from './ui/ErrorBoundary'
import { SystemCenter } from './ui/SystemCenter'
import { HistoryPanel, type HistoryEntry } from './conversation/HistoryPanel'
import type { AiActivity } from './core/types'
import type { AppSettings } from './core/store'
import './styles/index.css'

const WS_URL = `ws://${location.hostname}:9528/v2/ws`
let idCounter = 0
const nextId = () => `msg_${++idCounter}`

function AppInner() {
  const actions = useActions()
  const clientRef = useRef<RuntimeAdapter | null>(null)
  const audioRef = useRef<AudioPlayer | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [histories, setHistories] = useState<HistoryEntry[]>([])
  const [historyUid, setHistoryUid] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [activeSection, setActiveSection] = useState<WorkspaceSection>('chat')
  const [accessoryParts, setAccessoryParts] = useState<Record<string, string>>({})
  const [accessoryState, setAccessoryState] = useState<Record<string, boolean>>({})
  const settings = useSelector(selectSettings)
  const settingsRef = useRef(settings)
  settingsRef.current = settings

  // Initialize Runtime adapter and Audio player
  useEffect(() => {
    const client = new RuntimeAdapter(WS_URL)
    const audio = new AudioPlayer()
    clientRef.current = client
    audioRef.current = audio

    const unsub1 = eventBus.on('connection:change', ({ connected }) => {
      actions.setConnection(connected ? 'connected' : 'disconnected')
      if (connected) {
        client.sendCommand('get_histories', {})
        // Sync proactive settings to backend on reconnect (use ref for latest)
        const s = settingsRef.current
        client.sendCommand('set_proactive', { enabled: s.proactive })
        client.sendCommand('set_proactive_idle', { seconds: s.proactiveIdleTime })
      }
    })

    const unsub2 = eventBus.on('runtime:status', ({ status, message }) => {
      const activityMap: Record<string, AiActivity> = {
        idle: 'idle', processing: 'thinking', thinking: 'thinking', speaking: 'speaking',
      }
      const activity = activityMap[status] || 'idle'
      actions.setActivity(activity)
      if (message) actions.setStatusMessage(message)
    })

    const unsub3 = eventBus.on('runtime:message', ({ text, reasoning }) => {
      actions.setStatusMessage('')
      actions.updateLastAssistant(text, reasoning)
    })

    const unsub4 = eventBus.on('runtime:chunk', ({ text }) => {
      actions.setActivity('speaking')
      actions.updateLastAssistant(text)
    })

    const unsub5 = eventBus.on('audio:play', ({ audio: b64, format }) => {
      actions.setAudioPlaying(true)
      audio.enqueue(b64, format)
    })

    const unsub6 = eventBus.on('audio:stop', () => {
      audio.stop()
      actions.setAudioPlaying(false)
    })

    const unsub7 = eventBus.on('runtime:tts_start', () => {
      actions.setActivity('speaking')
      actions.setAudioPlaying(true)
    })

    const unsub8 = eventBus.on('runtime:tts_end', () => {})

    const unsub9 = eventBus.on('runtime:character_state', ({ activity, emotion, intensity, expression, motion }) => {
      actions.setCharacterActivity(activity as AiActivity)
      actions.setCharacter(emotion, intensity, expression, motion)
    })

    const unsub11 = eventBus.on('runtime:user_message', ({ text }) => {
      if (!text) return
      actions.addMessage({ id: nextId(), role: 'user', text, timestamp: Date.now() })
      actions.addMessage({ id: nextId(), role: 'assistant', text: '', timestamp: Date.now() })
    })

    const unsub10 = eventBus.on('runtime:error', ({ message }) => {
      actions.setActivity('idle')
      actions.addMessage({ id: nextId(), role: 'system', text: `[Error] ${message}`, timestamp: Date.now() })
    })

    // Handle command responses (e.g., get_histories)
    const unsub12 = eventBus.on('runtime:command_response', ({ action, data }) => {
      if (action === 'get_histories' && Array.isArray((data as any)?.histories)) {
        const h = (data as any).histories as HistoryEntry[]
        setHistories(h)
        if (h.length > 0 && !historyUid) {
          setHistoryUid(h[0].uid)
        }
      }
    })

    audio.setHandlers({
      onStart() { actions.setAudioPlaying(true); eventBus.emit('audio:start', undefined) },
      onEnd() { actions.setAudioPlaying(false); actions.setAudioVolume(0); eventBus.emit('audio:end', undefined) },
      onVolume(vol) { actions.setAudioVolume(vol); eventBus.emit('audio:volume', { volume: vol }) },
    })

    // Load persisted settings on startup
    fetch('/api/settings').then(r => r.json()).then(data => {
      const s = data.settings || {}
      for (const [key, value] of Object.entries(s)) {
        try { actions.setSetting(key as keyof AppSettings, value) } catch (_) {}
      }
      // Sync proactive to backend (handles case where WS already connected)
      if (clientRef.current) {
        if ('proactive' in s) {
          clientRef.current.sendCommand('set_proactive', { enabled: s.proactive })
        }
        if ('proactiveIdleTime' in s) {
          clientRef.current.sendCommand('set_proactive_idle', { seconds: s.proactiveIdleTime })
        }
      }
    }).catch(() => {})

    client.connect()

    // Listen for accessory events
    const unsubAccessoryLoaded = eventBus.on('accessory:loaded', ({ parts, state }) => {
      setAccessoryParts(parts)
      setAccessoryState(state)
    })
    const unsubAccessoryChanged = eventBus.on('accessory:state_changed', ({ parts, state }) => {
      setAccessoryParts(parts)
      setAccessoryState(state)
    })

    return () => {
      unsub1(); unsub2(); unsub3(); unsub4(); unsub5(); unsub6()
      unsub7(); unsub8(); unsub9(); unsub10(); unsub11(); unsub12()
      unsubAccessoryLoaded(); unsubAccessoryChanged()
      client.disconnect(); audio.stop()
    }
  }, [])

  const handleSend = useCallback((text: string) => {
    const client = clientRef.current
    const audio = audioRef.current
    if (!client) return
    // Ensure AudioContext is ready (browser autoplay policy)
    audio?.resume()
    actions.setActivity('thinking')
    actions.setStatusMessage('Processing...')
    actions.addMessage({ id: nextId(), role: 'user', text, timestamp: Date.now() })
    actions.addMessage({ id: nextId(), role: 'assistant', text: '', timestamp: Date.now() })
    client.sendText(text)
  }, [])

  const handleInterrupt = useCallback(() => {
    const client = clientRef.current
    const audio = audioRef.current
    audio?.stop()
    client?.sendInterrupt()
    actions.setActivity('idle')
    actions.setStatusMessage('')
  }, [])

  const handleAccessoryToggle = useCallback((label: string) => {
    eventBus.emit('accessory:toggle', { label })
  }, [])

  const handleSettingsOpen = useCallback(() => {
    setSettingsOpen(true)
    eventBus.emit('accessory:refresh', undefined)
  }, [])

  const handleSettingChange = useCallback((key: string, value: unknown) => {
    const client = clientRef.current
    actions.setSetting(key as keyof AppSettings, value)

    if (key === 'alwaysOnTop') {
      window.electronAPI?.setAlwaysOnTop(value as boolean)
    } else if (key === 'activeCharacterId') {
      client?.sendCommand('switch_character', { character_id: value })
    } else if (key === 'live2dModel') {
      // Keep the bridge mapper aligned with the visual model. The LLM remains
      // model-agnostic, but its semantic intent must map through this profile.
      fetch('/api/set-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: value }),
      }).catch(() => {})
      eventBus.emit('character:switch_model', { name: value as string })
    } else if (key === 'proactive') {
      client?.sendCommand('set_proactive', { enabled: value })
    } else if (key === 'proactiveIdleTime') {
      client?.sendCommand('set_proactive_idle', { seconds: value })
    } else if (key === 'windowMode') {
      if (value === 'pet') {
        document.body.style.cursor = 'default'
        window.electronAPI?.setPetMode(true)
      } else {
        document.body.style.cursor = ''
        window.electronAPI?.setPetMode(false)
      }
    }
  }, [])

  // Persist settings to backend whenever they change
  useEffect(() => {
    const timer = setTimeout(() => {
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings }),
      }).catch(() => {})
    }, 500)
    return () => clearTimeout(timer)
  }, [settings])

  // Resume AudioContext on first user gesture (browser autoplay policy)
  const handleUserGesture = useCallback(() => {
    const audio = audioRef.current
    audio?.resume()
  }, [])

  return (
    <div style={styles.wrapper} onClick={handleUserGesture}>
      <TitleBar />
      <Layout
        statusBar={<StatusBar />}
        characterArea={<CharacterView />}
        chatArea={
          <div style={{ display: 'flex', height: '100%', flexDirection: 'column' }}>
            <ChatView />
          </div>
        }
        inputBar={
          <InputBar onSend={handleSend} onInterrupt={handleInterrupt} clientRef={clientRef} />
        }
        systemArea={
          <SystemCenter
            sendCommand={(action, params = {}) => clientRef.current?.sendCommand(action, params)}
          />
        }
        activeSection={activeSection}
        onSectionChange={(section) => {
          setActiveSection(section)
          if (section === 'history') setHistoryOpen(true)
          if (section === 'settings') handleSettingsOpen()
        }}
      />
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onSettingChange={handleSettingChange}
        accessoryParts={accessoryParts}
        accessoryState={accessoryState}
        onAccessoryToggle={handleAccessoryToggle}
      />
      {historyOpen && (
        <div style={styles.overlay} onClick={() => setHistoryOpen(false)}>
          <div style={styles.overlayPanel} onClick={e => e.stopPropagation()}>
            <div style={styles.overlayHeader}>
              <span style={{ fontWeight: 600 }}>对话记忆</span>
              <button type="button" onClick={() => setHistoryOpen(false)}
                style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: '1.1rem' }}>
                ✕
              </button>
            </div>
            <HistoryPanel
              histories={histories}
              activeUid={historyUid}
              loading={historyLoading}
              onLoad={(uid) => {
                setHistoryUid(uid)
                setHistoryLoading(true)
                clientRef.current?.sendCommand('load_history', { uid })
                setTimeout(() => { setHistoryLoading(false); setHistoryOpen(false) }, 500)
              }}
              onDelete={(uid) => {
                clientRef.current?.sendCommand('delete_history', { uid })
                setHistories(prev => prev.filter(h => h.uid !== uid))
              }}
              onCreate={() => {
                clientRef.current?.sendCommand('create_history', {})
                setHistoryLoading(true)
                setTimeout(() => {
                  clientRef.current?.sendCommand('get_histories', {})
                  setHistoryLoading(false)
                  setHistoryOpen(false)
                }, 500)
              }}
            />
          </div>
        </div>
      )}
      <DebugPanel />
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <StoreProvider>
        <AppInner />
      </StoreProvider>
    </ErrorBoundary>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: { height: '100%', display: 'flex', flexDirection: 'column' },
  overlay: {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 100, display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  },
  overlayPanel: {
    backgroundColor: '#18181c', borderRadius: '8px', padding: '16px',
    maxWidth: '400px', width: '90%', maxHeight: '80vh', overflow: 'hidden',
    display: 'flex', flexDirection: 'column',
  },
  overlayHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    paddingBottom: '8px', marginBottom: '8px', borderBottom: '1px solid #333',
    color: '#e0e0e0',
  },
}
