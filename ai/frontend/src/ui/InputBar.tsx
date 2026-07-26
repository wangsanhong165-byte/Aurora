import { useEffect, useRef, useState } from 'react'
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
  const isBusy = ['thinking', 'speaking', 'processing'].includes(activity)

  useEffect(() => {
    if (!isBusy) inputRef.current?.focus()
  }, [isBusy])

  useEffect(() => {
    if (!AudioRecorder.isSupported()) return
    const recorder = new AudioRecorder()
    recorderRef.current = recorder
    recorder.setCallbacks({
      onData(samples, sampleRate) { clientRef?.current?.sendAudioSamples(samples, sampleRate) },
      onEnd() { clientRef?.current?.sendAudioEnd() },
      onError(message) { console.warn('[Mic]', message) },
      onStateChange(state) { setRecorderState(state) },
    })
    return () => {
      recorder.stop()
      recorderRef.current = null
    }
  }, [clientRef])

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const text = value.trim()
    if (!text || isBusy) return
    onSend(text)
    setValue('')
  }

  const toggleMic = async () => {
    const recorder = recorderRef.current
    if (!recorder) return
    if (recorder.state === 'recording') recorder.stop()
    else await recorder.start()
  }

  return (
    <form className="message-composer" onSubmit={submit}>
      {isBusy ? (
        <button type="button" className="interrupt-button" onClick={onInterrupt}>
          停止当前回复
        </button>
      ) : (
        <>
          <input
            ref={inputRef}
            value={value}
            onChange={event => setValue(event.target.value)}
            placeholder="和 SoulLink 聊点什么…"
            aria-label="消息"
          />
          {recorderRef.current && settings.voiceInputEnabled && (
            <button type="button" className="composer-action" onClick={toggleMic}>
              {recorderState === 'recording' ? '停止录音' : '语音'}
            </button>
          )}
          <button type="submit" className="send-button" disabled={!value.trim()}>
            发送
          </button>
        </>
      )}
    </form>
  )
}
