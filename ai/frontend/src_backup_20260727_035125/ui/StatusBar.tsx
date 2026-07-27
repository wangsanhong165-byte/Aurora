import {
  useSelector,
  selectConnection,
  selectActivity,
  selectStatusMessage,
  selectAudioState,
} from '../core/store'
import type { ConnectionState, AiActivity } from '../core/types'

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  disconnected: '未连接',
  connecting: '连接中',
  connected: '已连接',
}

const ACTIVITY_LABEL: Record<AiActivity, string> = {
  idle: '待机',
  listening: '倾听',
  thinking: '思考中',
  speaking: '说话中',
  processing: '处理中',
}

export function StatusBar() {
  const connection = useSelector(selectConnection)
  const activity = useSelector(selectActivity)
  const statusMessage = useSelector(selectStatusMessage)
  const audio = useSelector(selectAudioState)

  return (
    <footer className="bottom-status">
      <div className="bottom-status-group">
        <span className={`status-dot ${connection === 'connected' ? 'good' : 'warn'}`} />
        <span>{CONNECTION_LABEL[connection]}</span>
      </div>
      <div className="bottom-status-group activity-state">
        <span className={`activity-pulse activity-${activity}`} />
        <span>{statusMessage || ACTIVITY_LABEL[activity]}</span>
      </div>
      <div className="bottom-status-group">
        <span>语音</span>
        <strong>{audio.isPlaying ? '播放中' : '空闲'}</strong>
      </div>
    </footer>
  )
}
