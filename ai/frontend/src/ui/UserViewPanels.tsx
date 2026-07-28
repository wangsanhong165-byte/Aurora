import { useEffect, useState } from 'react'

import { eventBus } from '../core/event-bus'
import { DrawerPanel } from './DrawerPanel'

type RequestCommand = (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>

type MemoryItem = {
  ref: string
  summary: string
  category: string
  pinned: boolean
  formedAt: string
  updatedAt: string
  lastUsedAt: string
  formationReason?: string
}

type MemoryView = {
  selectedCategory: string
  categories: Array<{ id: string; label: string }>
  items: MemoryItem[]
}

const EMPTY_MEMORY: MemoryView = { selectedCategory: 'all', categories: [], items: [] }

type CharacterSelfView = {
  currentState: string
  recentFocus: string[]
  persistentGoals: string[]
  recentChanges: string[]
  relationshipSummary?: string
}

type VoiceStatusView = {
  microphone: { label: string; status: string }
  voice: { label: string; status: string; name?: string }
  outputDevice: { label: string }
  interruptible: boolean
}

type CapabilityItem = {
  name: string
  description?: string
  status: string
  permission: string
  allowedProactively: boolean
  recentlyUsedAt?: string
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="empty-copy user-view-empty">{children}</p>
}

function formatDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso || '—' }
}

function categoryLabel(category: string): string {
  return ({ about_you: '关于你', shared: '共同经历', self: '角色自身', preferences: '偏好习惯', goals: '持续目标', pinned: '已置顶' })[category] || category
}

// ── Character Self Panel ─────────────────────────────────────────

export function CharacterSelfPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [view, setView] = useState<CharacterSelfView | null>(null)
  const refresh = () => requestCommand('get_character_self_view', {}).then(data => setView((data as any).view))

  useEffect(() => {
    const unsubMessage = eventBus.on('runtime:message', () => refresh())
    void refresh()
    return () => { unsubMessage() }
  }, [])

  return (
    <DrawerPanel title="角色" action={
      <button type="button" className="drawer-text-action" onClick={() => void refresh()}>刷新</button>
    }>
      {!view ? <EmptyState>正在了解角色此刻的状态…</EmptyState> : (
        <div className="user-view">
          <ViewSection title="当前状态"><p>{view.currentState}</p></ViewSection>
          <TextList title="最近关注" items={view.recentFocus} />
          <TextList title="持续目标" items={view.persistentGoals} />
          <TextList title="最近变化" items={view.recentChanges} />
          {view.relationshipSummary && (
            <ViewSection title="与你的关系"><p>{view.relationshipSummary}</p></ViewSection>
          )}
        </div>
      )}
    </DrawerPanel>
  )
}

// ── Memory Panel ────────────────────────────────────────────────────

export function MemoryPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [view, setView] = useState<MemoryView>(EMPTY_MEMORY)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<MemoryItem | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmForget, setConfirmForget] = useState(false)

  const refresh = (category = view.selectedCategory || 'all', search = query) => {
    setSelected(null)
    return requestCommand('get_memory_view', { category, query: search })
      .then(data => setView((data as any).view ?? EMPTY_MEMORY))
      .catch(() => {})
  }

  useEffect(() => {
    void refresh('all', '')
    const unsub = eventBus.on('connection:change', ({ connected }) => {
      if (connected) void refresh(view.selectedCategory || 'all', query)
    })
    return () => unsub()
  }, [])

  const choose = (item: MemoryItem) => {
    if (selected?.ref === item.ref) { setSelected(null); return }
    setSelected(item)
    setDraft(item.summary)
    setConfirmForget(false)
  }

  const closeEditor = () => setSelected(null)

  return (
    <DrawerPanel title="记忆">
      <div className="memory-view">
        <form onSubmit={event => { event.preventDefault(); refresh(view.selectedCategory, query) }}>
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索记忆…" />
          <button type="submit">搜索</button>
        </form>
        <div className="memory-categories" aria-label="记忆分类">
          {view.categories.map(item => (
            <button
              type="button"
              key={item.id}
              className={view.selectedCategory === item.id ? 'is-active' : ''}
              onClick={() => refresh(item.id)}
            >{item.label}</button>
          ))}
        </div>
        <div className="memory-view-list">
          {view.items.length === 0 && <EmptyState>这个分类里暂时没有记忆。</EmptyState>}
          {view.items.map(item => (
            <div key={item.ref}>
              <button type="button" onClick={() => choose(item)}>
                <span>{item.pinned ? '置顶 · ' : ''}{categoryLabel(item.category)}</span>
                <strong>{item.summary}</strong>
                <small>{formatDate(item.updatedAt)}</small>
              </button>
              {selected?.ref === item.ref && (
                <section className="memory-editor">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="eyebrow">记忆详情</span>
                    <button type="button" onClick={closeEditor}
                      style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0 }}>&times;</button>
                  </div>
                  <textarea value={draft} onChange={event => setDraft(event.target.value)} />
                  <dl className="memory-context">
                    <div><dt>形成于</dt><dd>{formatDate(selected.formedAt)}</dd></div>
                    <div><dt>最近使用</dt><dd>{formatDate(selected.lastUsedAt)}</dd></div>
                    <div><dt>形成原因</dt><dd>{selected.formationReason || '从相关对话中形成'}</dd></div>
                  </dl>
                  <div className="memory-editor-actions">
                    <button type="button" onClick={async () => {
                      await requestCommand('update_memory_view', { ref: selected.ref, content: draft })
                      setSelected(null); void refresh()
                    }}>保存修改</button>
                    <button type="button" onClick={async () => {
                      await requestCommand('update_memory_view', { ref: selected.ref, pinned: !selected.pinned })
                      setSelected(null); void refresh()
                    }}>{selected.pinned ? '取消置顶' : '置顶'}</button>
                    {!confirmForget ? (
                      <button type="button" onClick={() => setConfirmForget(true)}>遗忘…</button>
                    ) : (
                      <button type="button" className="danger" onClick={async () => {
                        await requestCommand('forget_memory_view', { ref: selected.ref })
                        setSelected(null); setConfirmForget(false); void refresh()
                      }}>确认遗忘</button>
                    )}
                  </div>
                </section>
              )}
            </div>
          ))}
        </div>
      </div>
    </DrawerPanel>
  )
}

// ── Voice Panel ──────────────────────────────────────────────────

export function VoicePanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [view, setView] = useState<VoiceStatusView | null>(null)
  useEffect(() => {
    void requestCommand('get_voice_status_view', {}).then(data => setView((data as any).view))
  }, [])
  return (
    <DrawerPanel title="语音">
      {!view ? <EmptyState>正在检查语音服务…</EmptyState> : (
        <div className="user-view status-view">
          <StatusLine label={view.microphone.label} value={statusLabel(view.microphone.status)} />
          <StatusLine label={view.voice.label} value={view.voice.name || statusLabel(view.voice.status)} />
          <StatusLine label="输出设备" value={view.outputDevice.label} />
          <StatusLine label="允许语音打断" value={view.interruptible ? '开启' : '关闭'} />
          <p className="view-note">音量和主动语音选项继续在设置中管理。</p>
        </div>
      )}
    </DrawerPanel>
  )
}

// ── Capability Panel ─────────────────────────────────────────────

export function CapabilityPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [items, setItems] = useState<CapabilityItem[]>([])
  const [toggling, setToggling] = useState<string | null>(null)
  const refresh = () => requestCommand('get_capability_view', {})
    .then(data => setItems((data as any).view?.items ?? []))

  useEffect(() => {
    void refresh()
  }, [])

  const toggleCapability = async (item: CapabilityItem) => {
    setToggling(item.name)
    setItems(prev => prev.map(i =>
      i.name === item.name ? { ...i, status: i.status === 'available' ? 'disabled' : 'available' } : i
    ))
    await requestCommand('set_tool_enabled', { name: item.name, enabled: item.status !== 'available' })
    await refresh()
    setToggling(null)
  }

  return (
    <DrawerPanel title="能力">
      <div className="capability-view">
        {items.length === 0 && <EmptyState>当前没有可用的外部能力。</EmptyState>}
        {items.map(item => {
          const isAvailable = item.status === 'available'
          return (
            <article key={item.name}>
              <div>
                <strong>{item.name}</strong>
                <p>{item.description || '由角色在需要时使用。'}</p>
                <small>
                  {item.permission === 'ask' ? '使用前询问' : '只读自动使用'}
                  {' · '}
                  {item.allowedProactively ? '允许主动使用' : '仅响应你的请求'}
                  {item.recentlyUsedAt ? ` · 最近使用 ${formatDate(item.recentlyUsedAt)}` : ''}
                </small>
              </div>
              <button
                type="button"
                className={isAvailable ? 'is-active' : ''}
                disabled={toggling === item.name}
                onClick={() => void toggleCapability(item)}
              >{isAvailable ? '已开启' : '已关闭'}</button>
            </article>
          )
        })}
      </div>
    </DrawerPanel>
  )
}

// ── Shared helpers ────────────────────────────────────────────────

function ViewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><h3>{title}</h3>{children}</section>
}

function TextList({ title, items }: { title: string; items: string[] }) {
  return (
    <ViewSection title={title}>
      {items.length ? <ul>{items.map(item => <li key={item}>{item}</li>)}</ul> : <p>暂时没有新的内容。</p>}
    </ViewSection>
  )
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return <div className="status-line"><span>{label}</span><strong>{value}</strong></div>
}

function statusLabel(status: string) {
  return status === 'ready' ? '正常' : status === 'unavailable' ? '不可用' : status
}
