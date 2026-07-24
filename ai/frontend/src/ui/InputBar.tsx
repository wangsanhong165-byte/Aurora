// Input Bar — text input with send/interrupt and microphone button

import { useState, useRef, useEffect } from 'react'
import { useSelector, selectActivity, selectSettings } from '../core/store'
import { AudioRecorder, type RecorderState } from '../audio/recorder'
import { RuntimeAdapter } from '../runtime/adapter'

export interface InputBarProps {
  onSend: (text: string) => void
  onInterrupt: () => void
  clientRef?: React.MutableRefObject<RuntimeAdapter | null>
}

export function InputBar({ onSend, onInterrupt, clientRef }: InputBarProps) {
  const [value, setValue] = useState('')
  const [recorderState, setRecorderState] = useState<RecorderState>('idle')
  const inputRef = useRef<HTMLInputElement>(null)
  const recorderRef = useRef<AudioRecorder | null>(null)
  const activity = useSelector(selectActivity)
  const settings = useSelector(selectSettings)
  const isBusy = activity === 'thinking' || activity === 'speaking' || activity === 'processing'

  useEffect(() => {
    if (!isBusy && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isBusy])

  // Initialize recorder
  useEffect(() => {
    if (AudioRecorder.isSupported()) {
      const recorder = new AudioRecorder()
      recorderRef.current = recorder

      recorder.setCallbacks({
        onData(samples, sampleRate) {
          const client = clientRef?.current
          if (client) {
            client.sendAudioSamples(samples, sampleRate)
          }
        },
        onEnd() {
          const client = clientRef?.current
          if (client) {
            client.sendAudioEnd()
          }
        },
        onError(msg) {
          console.warn('[Mic] Error:', msg)
        },
        onStateChange(state) {
          setRecorderState(state)
        },
      })
    }

    return () => {
      recorderRef.current?.stop()
      recorderRef.current = null
    }
  }, [clientRef])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
  }

  const toggleMic = async () => {
    const recorder = recorderRef.current
    if (!recorder) return
    if (recorder.state === 'recording') {
      recorder.stop()
    } else {
      await recorder.start()
    }
  }

  const isRecording = recorderState === 'recording'

  return (
    <form style={styles.form} onSubmit={handleSubmit}>
      <div style={styles.inputWrap}>
        {isBusy ? (
          <button type="button" style={styles.interruptBtn} onClick={onInterrupt} title="Interrupt">
            ■
          </button>
        ) : (
          <input
            ref={inputRef}
            style={styles.input}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Type a message..."
            disabled={isBusy}
          />
        )}
      </div>
      {recorderRef.current && settings.voiceInputEnabled && (
        <button
          type="button"
          style={{
            ...styles.micBtn,
            backgroundColor: isRecording ? '#8b3a3a' : '#333',
          }}
          onClick={toggleMic}
          title={isRecording ? 'Stop recording' : 'Start microphone'}
        >
          {isRecording ? '🔴' : '🎤'}
        </button>
      )}
      {!isBusy && (
        <button
          type="submit"
          style={{
            ...styles.sendBtn,
            opacity: value.trim() ? 1 : 0.4,
          }}
          disabled={!value.trim()}
          title="Send"
        >
          ↵
        </button>
      )}
    </form>
  )
}

const styles: Record<string, React.CSSProperties> = {
  form: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '0.75rem 1rem',
    backgroundColor: '#141418',
    borderTop: '1px solid #2a2a2e',
    flexShrink: 0,
  },
  inputWrap: {
    flex: 1,
  },
  input: {
    width: '100%',
    padding: '0.6rem 0.9rem',
    borderRadius: 10,
    border: '1px solid #333',
    backgroundColor: '#1e1e24',
    color: '#e0e0e0',
    fontSize: '0.9rem',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  sendBtn: {
    width: 38,
    height: 38,
    borderRadius: 10,
    border: 'none',
    backgroundColor: '#3a6a9e',
    color: '#fff',
    fontSize: '1.1rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background-color 0.2s',
    flexShrink: 0,
  },
  interruptBtn: {
    width: '100%',
    padding: '0.6rem 0.9rem',
    borderRadius: 10,
    border: '1px solid #8b3a3a',
    backgroundColor: '#2c1010',
    color: '#e74c3c',
    fontSize: '0.9rem',
    cursor: 'pointer',
    textAlign: 'center',
  },
  micBtn: {
    width: 38,
    height: 38,
    borderRadius: 10,
    border: 'none',
    color: '#fff',
    fontSize: '1rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
}
