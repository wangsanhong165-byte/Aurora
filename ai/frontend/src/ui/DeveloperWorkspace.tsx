import { useEffect, useState, type MutableRefObject } from 'react'

import { eventBus } from '../core/event-bus'
import { selectConnection, useSelector } from '../core/store'
import type { RuntimeAdapter } from '../runtime/adapter'
import { DrawerPanel } from './DrawerPanel'

type TurnSummary = {
  turnId: string
  createdAt: string
  phase: string
  origin: string
  summary: string
}

type TurnDetail = {
  turnId: string
  readOnly: boolean
  createdAt: string
  phase: string
  origin: string
  input: { text: string }
  response: { text: string; segments: Array<Record<string, string>> }
  performance: Record<string, unknown>
  memory: { retrieved: Array<Record<string, string>>; committed: Array<Record<string, string>> }
  tools: Array<Record<string, unknown>>
  prompt: { view: string; contextBudget: Record<string, unknown> }
  usage: Record<string, unknown>
  timeline: Array<{ event: string; offsetMs: number; durationMs?: number }>
  warnings: string[]
  error?: { code: string; message: string } | null
  retention: { days: number; maximumTurns: number }
}

export function DeveloperWorkspace({
  clientRef,
}: {
  clientRef: MutableRefObject<RuntimeAdapter | null>
}) {
  const [turns, setTurns] = useState<TurnSummary[]>([])
  const [detail, setDetail] = useState<TurnDetail | null>(null)
  const [diagnostics, setDiagnostics] = useState<any>(null)
  const connected = useSelector(selectConnection) === 'connected'
  const [errors, setErrors] = useState<Array<{ code: string; message: string }>>([])
  const [services, setServices] = useState<any[]>([])

  const refresh = () => {
    clientRef.current?.sendCommand('get_turns', { limit: 100 })
    clientRef.current?.sendCommand('get_runtime_diagnostics', {})
    window.electronAPI?.getStatus?.()
      .then((result: any) => setServices(result?.services ?? []))
      .catch(() => setServices([]))
  }

  useEffect(() => {
    const unsubCommand = eventBus.on('runtime:command_response', ({ action, data }) => {
      if (action === 'get_turns') {
        const next = Array.isArray((data as any).turns) ? (data as any).turns : []
        setTurns(next)
        if (!detail && next[0]) {
          clientRef.current?.sendCommand('get_turn_detail', { turn_id: next[0].turnId })
        }
      } else if (action === 'get_turn_detail') {
        setDetail((data as any).turn ?? null)
      } else if (action === 'get_runtime_diagnostics') {
        setDiagnostics(data)
      }
    })
    const unsubError = eventBus.on('runtime:error', error =>
      setErrors(items => [error, ...items].slice(0, 20))
    )
    refresh()
    const timer = window.setInterval(refresh, 10000)
    return () => {
      unsubCommand()
      unsubError()
      window.clearInterval(timer)
    }
  }, [])

  return (
    <DrawerPanel
      title="开发者工作台"
      action={<button type="button" className="drawer-text-action" onClick={refresh}>刷新</button>}
    >
      <div className="developer-workspace">
        <section className="developer-overview">
          <DevMetric label="WebSocket" value={connected ? '已连接' : '未连接'} />
          <DevMetric label="Runtime" value={diagnostics?.runtime?.idle ? '空闲' : '处理中'} />
          <DevMetric
            label="Turn"
            value={diagnostics?.runtime?.activeTurn?.turnId?.slice(0, 8)
              ?? String(diagnostics?.runtime?.turnCount ?? turns.length)}
          />
          <DevMetric label="服务" value={services.length ? `${services.filter(isHealthy).length}/${services.length}` : '浏览器预览'} />
        </section>

        <section className="turn-browser">
          <div className="turn-list">
            <h3>CharacterTurn</h3>
            {turns.length === 0 && <p className="empty-copy">完成一次对话后会生成只读记录。</p>}
            {turns.map(turn => (
              <button
                type="button"
                key={turn.turnId}
                className={detail?.turnId === turn.turnId ? 'is-active' : ''}
                onClick={() => clientRef.current?.sendCommand('get_turn_detail', { turn_id: turn.turnId })}
              >
                <span>{turn.phase} · {turn.origin}</span>
                <strong>{turn.summary || '语音输入'}</strong>
                <small>{new Date(turn.createdAt).toLocaleString('zh-CN')}</small>
              </button>
            ))}
          </div>
          <div className="turn-detail">
            {!detail ? <p className="empty-copy">选择一条 Turn 查看详情。</p> : (
              <>
                <DevSection title="当前回合">
                  <p>{detail.input.text || '语音输入'} → {detail.response.text || '无文本响应'}</p>
                  <small>只读 · {detail.phase} · {detail.turnId.slice(0, 8)}</small>
                </DevSection>
                <DevSection title="状态时间线">
                  <ol className="trace-timeline">
                    {detail.timeline.map((item, index) => (
                      <li key={`${item.event}-${index}`}>
                        <span>{item.event}</span>
                        <small>{Math.round(item.offsetMs)} ms{item.durationMs != null ? ` · ${Math.round(item.durationMs)} ms` : ''}</small>
                      </li>
                    ))}
                  </ol>
                </DevSection>
                <DevSection title="PromptBundle">
                  <p>内容已脱敏；仅显示上下文预算。</p>
                  <KeyValues value={detail.prompt.contextBudget} />
                </DevSection>
                <DevSection title="模型响应与解析">
                  <p>{detail.response.text || '无文本响应'}</p>
                  <KeyValues value={detail.usage} />
                </DevSection>
                <DevSection title="PerformancePlan">
                  <KeyValues value={detail.performance} />
                </DevSection>
                <DevSection title="Memory Retrieve / Commit">
                  <p>检索 {detail.memory.retrieved.length} 条 · 提交 {detail.memory.committed.length} 条</p>
                  {[...detail.memory.retrieved, ...detail.memory.committed].map((item, index) =>
                    <small key={index}>{item.type || 'memory'} · {item.summary}</small>
                  )}
                </DevSection>
                <DevSection title="ASR / TTS">
                  <p>{detail.timeline.some(item => item.event.includes('ASR')) ? '包含 ASR 生命周期' : '文本输入'}</p>
                  <p>{detail.timeline.some(item => item.event.includes('TTS')) ? 'TTS 已生成音频' : '本轮无 TTS 音频'}</p>
                </DevSection>
                {(detail.warnings.length > 0 || detail.error) && (
                  <DevSection title="错误与警告">
                    {detail.error && <p>{detail.error.code} · {detail.error.message}</p>}
                    {detail.warnings.map(item => <small key={item}>{item}</small>)}
                  </DevSection>
                )}
              </>
            )}
          </div>
        </section>

        <DevSection title="服务健康">
          {diagnostics?.providers?.map((provider: any) => (
            <small key={provider.name}>{provider.name} · {provider.status} · {provider.adapter}</small>
          ))}
          {services.map((service: any) => (
            <small key={service.name}>{service.name} · {service.status}</small>
          ))}
        </DevSection>
        {errors.length > 0 && (
          <DevSection title="本次连接的错误">
            {errors.map((error, index) => <small key={`${error.code}-${index}`}>{error.code} · {error.message}</small>)}
          </DevSection>
        )}
        <p className="developer-retention">
          Turn 记录默认保留 30 天、最多 500 条；只读查询，不提供 Runtime 状态修改或逐帧参数回放。
        </p>
      </div>
    </DrawerPanel>
  )
}

function DevMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

function DevSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="dev-section"><h3>{title}</h3>{children}</section>
}

function KeyValues({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="dev-key-values">
      {Object.entries(value ?? {}).map(([key, item]) => (
        <div key={key}><dt>{key}</dt><dd>{String(item ?? '—')}</dd></div>
      ))}
    </dl>
  )
}

function isHealthy(service: any) {
  return ['running', 'healthy', 'ok', 'ready'].includes(String(service.status).toLowerCase())
}
