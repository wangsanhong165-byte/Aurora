import { useEffect, useRef } from 'react'
import { useSelector, selectMessages } from '../core/store'
import type { ChatMessage } from '../core/types'

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  return (
    <article className={`chat-message ${isUser ? 'is-user' : ''} ${isSystem ? 'is-system' : ''}`}>
      <div className="message-meta">
        <strong>{isUser ? '你' : isSystem ? '系统' : 'SoulLink'}</strong>
        <time>{new Date(message.timestamp).toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
        })}</time>
      </div>
      <p>{message.text || (!isUser && !isSystem ? '正在组织语言…' : '')}</p>
      {!isUser && !isSystem && message.reasoning && (
        <details className="reasoning">
          <summary>查看思考摘要</summary>
          <p>{message.reasoning}</p>
        </details>
      )}
    </article>
  )
}

export function ChatView() {
  const messages = useSelector(selectMessages)
  const listRef = useRef<HTMLDivElement>(null)
  const visible = messages.slice(-4)
  const lastText = visible.at(-1)?.text ?? ''

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [visible.length, lastText])

  return (
    <div className="chat-view" ref={listRef}>
      {visible.length === 0 ? (
        <div className="conversation-welcome">
          <span>准备好了</span>
          <p>和我说点什么吧，我会结合记忆与你自然交流。</p>
        </div>
      ) : visible.map(message => <Message key={message.id} message={message} />)}
    </div>
  )
}
