import { useEffect, useRef, useCallback, useState } from 'react'
import { StoreProvider, useActions, useSelector, selectSettings } from './core/store'
import { eventBus } from './core/event-bus'
import { RuntimeAdapter } from './runtime/adapter'
import { AudioPlayer } from './audio/player'
import { StatusBar } from './ui/StatusBar'
import { TitleBar } from './ui/TitleBar'
import { ErrorBoundary } from './ui/ErrorBoundary'
import type { HistoryEntry } from './conversation/HistoryPanel'
import type { AiActivity } from './core/types'
import type { AppSettings } from './core/store'
import type { ChatMessage } from './core/types'
import { CompanionWorkspace } from './ui/CompanionWorkspace'
import { resolveHistoryCommand } from './conversation/history-command'
import './styles/index.css'

const WS_URL = `ws://${location.hostname}:9528/client-ws`
let idCounter = 0
const nextId = () => `msg_${++idCounter}`

function AppInner() {
  const actions = useActions()
  const clientRef = useRef<RuntimeAdapter | null>(null)
  const audioRef = useRef<AudioPlayer | null>(null)
  const [histories, setHistories] = useState<HistoryEntry[]>([])
  const [historyUid, setHistoryUid] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [subtitleText, setSubtitleText] = useState('')
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
      setSubtitleText(text)
    })

    const unsub4 = eventBus.on('runtime:chunk', ({ text }) => {
      actions.setActivity('speaking')
      actions.updateLastAssistant(text)
      setSubtitleText(text)
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
        setHistoryUid(current =>
          h.some(entry => entry.uid === current) ? current : h[0]?.uid || ''
        )
        setHistoryLoading(false)
        return
      }

      const effect = resolveHistoryCommand(action, data)
      if (effect) {
        setHistoryUid(effect.activeUid)
        setHistoryLoading(false)
        if (effect.clearMessages) actions.clearMessages()
        if (effect.messages) {
          const messages = effect.messages.flatMap((item, index): ChatMessage[] => {
            if (!item || typeof item !== 'object') return []
            const record = item as Record<string, unknown>
            const role = record.role
            const content = record.content
            if ((role !== 'user' && role !== 'assistant' && role !== 'system') || typeof content !== 'string') {
              return []
            }
            return [{
              id: `history_${effect.activeUid}_${index}`,
              role,
              text: content,
              timestamp: typeof record.timestamp === 'number' ? record.timestamp : Date.now() + index,
            }]
          })
          actions.setMessages(messages)
        }
        if (effect.refreshHistories) client.sendCommand('get_histories', {})
        setHistoryRevision(current => current + 1)
      } else if (action === 'delete_history') {
        setHistoryLoading(false)
        const deletedUid = String(data.history_uid ?? '')
        setHistoryUid(current => {
          if (current !== deletedUid) return current
          actions.clearMessages()
          return ''
        })
        client.sendCommand('get_histories', {})
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
      if ('alwaysOnTop' in s) {
        window.electronAPI?.setAlwaysOnTop(Boolean(s.alwaysOnTop))
      }
      if ('windowMode' in s) {
        window.electronAPI?.setPetMode(s.windowMode === 'pet')
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
      {settings.windowMode !== 'pet' && <TitleBar />}
      <CompanionWorkspace
        settings={settings}
        clientRef={clientRef}
        histories={histories}
        historyUid={historyUid}
        historyLoading={historyLoading}
        historyRevision={historyRevision}
        subtitleText={subtitleText}
        accessoryParts={accessoryParts}
        accessoryState={accessoryState}
        onSend={handleSend}
        onInterrupt={handleInterrupt}
        onLoadHistory={(uid) => {
          setHistoryLoading(true)
          clientRef.current?.sendCommand('load_history', { history_uid: uid })
        }}
        onDeleteHistory={(uid) => {
          setHistoryLoading(true)
          clientRef.current?.sendCommand('delete_history', { history_uid: uid })
        }}
        onCreateHistory={() => {
          setHistoryLoading(true)
          clientRef.current?.sendCommand('create_history', {})
        }}
        onSettingChange={handleSettingChange}
        onAccessoryToggle={handleAccessoryToggle}
      />
      {settings.windowMode !== 'pet' && <StatusBar />}
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
}
