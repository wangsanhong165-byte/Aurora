import { useEffect, useMemo, useState } from 'react'
import { eventBus } from '../core/event-bus'

type MemoryItem = {
  id: number
  memory_type: string
  content: string
  importance: number
  confidence: number
}

type Metrics = {
  usage?: {
    totals?: {
      turns?: number
      prompt_tokens?: number
      completion_tokens?: number
      cached_tokens?: number
      estimated_cost_usd?: number
    }
    recent?: Array<{ context_budget?: { estimated_tokens?: number; max_tokens?: number } }>
  }
  memory?: { active_count?: number }
}

type ToolItem = {
  name: string
  description: string
  risk: string
  enabled: boolean
  allowed_in_initiative: boolean
}

type ServiceItem = {
  name: string
  status: string
  restartCount?: number
  consecutiveHealthFailures?: number
  lastHealthError?: string
}

const formatNumber = (value = 0) => new Intl.NumberFormat('zh-CN', {
  notation: value > 9999 ? 'compact' : 'standard',
  maximumFractionDigits: 1,
}).format(value)

export function SystemCenter({
  sendCommand,
}: {
  sendCommand: (action: string, params?: Record<string, unknown>) => void
}) {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [metrics, setMetrics] = useState<Metrics>({})
  const [services, setServices] = useState<ServiceItem[]>([])
  const [tools, setTools] = useState<ToolItem[]>([])
  const [expanded, setExpanded] = useState<'memory' | 'tools' | 'usage' | null>(null)
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  const refresh = () => {
    sendCommand('get_memories', { limit: 100 })
    sendCommand('get_system_metrics')
    sendCommand('get_tools')
    window.electronAPI?.getStatus?.()
      .then((status: any) => setServices(status?.services ?? []))
      .catch(() => setServices([]))
  }

  useEffect(() => {
    const unsub = eventBus.on('runtime:management.result', ({ action, data }) => {
      if (action === 'get_memories') {
        const items = Array.isArray((data as any)?.memories) ? (data as any).memories : []
        setMemories(items)
        setDrafts(Object.fromEntries(items.map((item: MemoryItem) => [item.id, item.content])))
      } else if (action === 'get_system_metrics') {
        setMetrics((data ?? {}) as Metrics)
      } else if (action === 'get_tools') {
        setTools(Array.isArray((data as any)?.tools) ? (data as any).tools : [])
      } else if (['set_tool_enabled', 'update_memory', 'forget_memory'].includes(action)) {
        refresh()
      }
    })
    refresh()
    const timer = window.setInterval(refresh, 15000)
    return () => {
      unsub()
      window.clearInterval(timer)
    }
  }, [])

  const totals = metrics.usage?.totals ?? {}
  const context = metrics.usage?.recent?.[0]?.context_budget
  const enabledTools = tools.filter(tool => tool.enabled).length
  const healthyServices = services.filter(service =>
    ['running', 'healthy', 'ok', 'ready'].includes(service.status?.toLowerCase())
  ).length
  const serviceTone = services.length > 0 && healthyServices === services.length ? 'good' : 'warn'
  const memoryCount = metrics.memory?.active_count ?? memories.length
  const contextPercent = Math.min(100, Math.round(
    ((context?.estimated_tokens ?? 0) / Math.max(1, context?.max_tokens ?? 32000)) * 100
  ))
  const lastMemories = useMemo(() => memories.slice(0, 12), [memories])

  return (
    <div className="system-center">
      <header className="system-heading">
        <div>
          <span className="eyebrow">实时状态</span>
          <h2>运行概览</h2>
        </div>
        <button type="button" className="text-button" onClick={refresh}>刷新</button>
      </header>

      <section className="health-summary">
        <div className={`status-dot ${serviceTone}`} />
        <div>
          <strong>{services.length ? `${healthyServices}/${services.length} 项服务正常` : '等待桌面服务'}</strong>
          <span>{services.length ? '系统每 15 秒自动检查' : '浏览器预览无法读取进程状态'}</span>
        </div>
      </section>

      <div className="summary-list">
        <SummaryRow
          label="上下文"
          value={`${formatNumber(context?.estimated_tokens)} tokens`}
          detail={`${contextPercent}%`}
          onClick={() => setExpanded(expanded === 'usage' ? null : 'usage')}
        />
        {expanded === 'usage' && (
          <div className="rail-detail">
            <Detail label="累计轮次" value={formatNumber(totals.turns)} />
            <Detail label="输入 / 输出" value={`${formatNumber(totals.prompt_tokens)} / ${formatNumber(totals.completion_tokens)}`} />
            <Detail label="缓存" value={formatNumber(totals.cached_tokens)} />
            <Detail label="估算费用" value={`$${Number(totals.estimated_cost_usd ?? 0).toFixed(4)}`} />
          </div>
        )}

        <SummaryRow
          label="人格记忆"
          value={`${memoryCount} 条`}
          detail="可管理"
          onClick={() => setExpanded(expanded === 'memory' ? null : 'memory')}
        />
        {expanded === 'memory' && (
          <div className="rail-detail memory-detail">
            {lastMemories.length === 0 && <p className="empty-copy">暂时没有结构化记忆</p>}
            {lastMemories.map(memory => (
              <article className="memory-row" key={memory.id}>
                <span>{memory.memory_type}</span>
                <textarea
                  value={drafts[memory.id] ?? memory.content}
                  onChange={event => setDrafts(current => ({ ...current, [memory.id]: event.target.value }))}
                  aria-label={`编辑记忆 ${memory.id}`}
                />
                <div className="memory-actions">
                  <button type="button" onClick={() => sendCommand('update_memory', {
                    memory_id: memory.id,
                    content: drafts[memory.id],
                  })}>保存</button>
                  <button type="button" className="danger" onClick={() => sendCommand('forget_memory', {
                    memory_id: memory.id,
                  })}>遗忘</button>
                </div>
              </article>
            ))}
          </div>
        )}

        <SummaryRow
          label="LLM 工具"
          value={`${enabledTools}/${tools.length} 已启用`}
          detail="权限"
          onClick={() => setExpanded(expanded === 'tools' ? null : 'tools')}
        />
        {expanded === 'tools' && (
          <div className="rail-detail">
            {tools.length === 0 && <p className="empty-copy">当前没有可用工具</p>}
            {tools.map(tool => (
              <label className="tool-row" key={tool.name}>
                <span>
                  <strong>{tool.name}</strong>
                  <small>{tool.allowed_in_initiative ? '可用于主动系统' : '仅响应用户请求'} · {tool.risk}</small>
                </span>
                <input
                  type="checkbox"
                  checked={tool.enabled}
                  onChange={event => sendCommand('set_tool_enabled', {
                    name: tool.name,
                    enabled: event.target.checked,
                  })}
                />
              </label>
            ))}
          </div>
        )}
      </div>

      {services.some(service => service.lastHealthError) && (
        <div className="service-warning">
          <span>服务提醒</span>
          <strong>{services.filter(service => service.lastHealthError).length} 项需要关注</strong>
        </div>
      )}
    </div>
  )
}

function SummaryRow({
  label,
  value,
  detail,
  onClick,
}: {
  label: string
  value: string
  detail: string
  onClick: () => void
}) {
  return (
    <button type="button" className="summary-row" onClick={onClick}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </button>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="detail-row"><span>{label}</span><strong>{value}</strong></div>
}
