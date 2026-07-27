import { useEffect, useRef, useState } from 'react'
import { Mic, Send, Square } from 'lucide-react'
import { useSelector, selectActivity, selectSettings } from '../core/store'
import type { RecorderState } from '../audio/recorder'

export interface InputBarProps {
  onSend: (text: string) => void
  onInterrupt: () => void
  recorderState: RecorderState
  recordingSupported: boolean
  onToggleRecording: () => void | Promise<void>
}

export function InputBar({
  onSend, onInterrupt, recorderState, recordingSupported, onToggleRecording,
}: InputBarProps) {
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const activity = useSelector(selectActivity)
  const settings = useSelector(selectSettings)
  const isBusy = ['thinking', 'speaking', 'processing'].includes(activity)

  useEffect(() => {
    if (!isBusy) inputRef.current?.focus()
  }, [isBusy])

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const text = value.trim()
    if (!text || isBusy) return
    onSend(text)
    setValue('')
  }

  return (
    <form className="message-composer" onSubmit={submit}>
      {isBusy ? (
        <button type="button" className="interrupt-button" onClick={onInterrupt}>
          <Square size={14} aria-hidden="true" />
          停止回复
        </button>
      ) : (
        <>
          <input
            ref={inputRef}
            value={value}
            onChange={event => setValue(event.target.value)}
            placeholder="想聊点什么？"
            aria-label="消息"
          />
          {recordingSupported && settings.voiceInputEnabled && (
            <button
              type="button"
              className="composer-action"
              onClick={onToggleRecording}
              aria-label={recorderState === 'recording' ? '停止录音' : '语音输入'}
              title={recorderState === 'recording' ? '停止录音' : '语音输入'}
            >
              {recorderState === 'recording'
                ? <Square size={16} aria-hidden="true" />
                : <Mic size={17} aria-hidden="true" />}
            </button>
          )}
          <button type="submit" className="send-button" disabled={!value.trim()} aria-label="发送">
            <Send size={17} aria-hidden="true" />
          </button>
        </>
      )}
    </form>
  )
}
