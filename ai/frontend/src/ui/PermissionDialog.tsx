import { useEffect, useMemo, useState } from 'react'

import { eventBus } from '../core/event-bus'

type PermissionRequest = {
  requestId: string
  capability: string
  args: Record<string, unknown>
  risk: string
}

const RISK_COPY: Record<string, string> = {
  read_only: '只读取信息，不会修改外部内容。',
  confirm: '此操作可能读取或修改你指定的内容，只会执行这一次。',
  write: '此操作会修改外部内容，请确认目标和影响。',
  destructive: '此操作可能造成难以恢复的更改，请谨慎确认。',
}

export function PermissionDialog() {
  const [queue, setQueue] = useState<PermissionRequest[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const current = queue[0]

  useEffect(() => eventBus.on('runtime:permission_requested', request => {
    setQueue(items => [...items, request])
  }), [])

  const scope = useMemo(() => {
    if (!current) return []
    return Object.keys(current.args).slice(0, 6).map(key =>
      key.replace(/_/g, ' ')
    )
  }, [current])

  if (!current) return null

  const resolve = async (approved: boolean) => {
    setSubmitting(true)
    setError('')
    try {
      const response = await fetch(
        `/api/tool-confirmations/${encodeURIComponent(current.requestId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved }),
        },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload.resolved !== true) {
        throw new Error('permission request is no longer pending')
      }
      setQueue(items => items.slice(1))
    } catch {
      setError('没有成功提交选择，请重试；当前操作尚未执行。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="permission-backdrop" role="presentation">
      <section
        className="permission-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="permission-title"
      >
        <span className="eyebrow">需要你的允许</span>
        <h2 id="permission-title">{current.capability}</h2>
        <dl>
          <div>
            <dt>目的</dt>
            <dd>角色希望使用这项能力来完成你当前的请求。</dd>
          </div>
          <div>
            <dt>风险</dt>
            <dd>{RISK_COPY[current.risk] ?? RISK_COPY.confirm}</dd>
          </div>
          <div>
            <dt>涉及范围</dt>
            <dd>{scope.length ? scope.join('、') : '当前请求提供的信息'}</dd>
          </div>
        </dl>
        <p className="permission-note">拒绝不会中断对话，角色会尝试说明限制或提供替代方案。</p>
        {error && <p className="permission-error" role="alert">{error}</p>}
        <div className="permission-actions">
          <button type="button" disabled={submitting} onClick={() => void resolve(false)}>拒绝</button>
          <button type="button" disabled={submitting} className="primary" onClick={() => void resolve(true)}>
            {submitting ? '正在提交…' : '允许一次'}
          </button>
        </div>
      </section>
    </div>
  )
}
