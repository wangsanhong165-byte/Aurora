import { useEffect, useState } from 'react'

import { eventBus } from '../core/event-bus'
import { DrawerPanel } from './DrawerPanel'

type RequestCommand = (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>

type CharacterSelfView = {
  currentState: string
  recentFocus: string[]
  persistentGoals: string[]
  recentChanges: string[]
  relationshipSummary?: string
}

type MemoryItem = {
  ref: string
  category: string
  summary: string
  updatedAt: string
  formedAt?: string
  lastUsedAt?: string
  formationReason?: string
  pinned: boolean
  editable: boolean
}

type MemoryView = {
  query: string
  selectedCategory: string
  categories: Array<{ id: string; label: string }>
  items: MemoryItem[]
}

type VoiceStatusView = {
  microphone: { status: string; label: string }
  voice: { status: string; label: string; name: string }
  outputDevice: { status: string; label: string }
  interruptible: boolean
}

type CapabilityItem = {
  name: string
  description: string
  status: string
  permission: string
  recentlyUsedAt?: string
  allowedProactively: boolean
}

const EMPTY_MEMORY: MemoryView = {
  query: '',
  selectedCategory: 'all',
  categories: [],
  items: [],
}

function EmptyState({ children }: { children: string }) {
  return <p className="empty-copy user-view-empty">{children}</p>
}

export function CharacterSelfPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [view, setView] = useState<CharacterSelfView | null>(null)
  useEffect(() => {
    const unsubMessage = eventBus.on('runtime:message', () =>
      void requestCommand('get_character_self_view', {}).then(data => setView((data as any).view))
    )
    void requestCommand('get_character_self_view', {}).then(data => setView((data as any).view))
    return () => {
      unsubMessage()
    }
  }, [])
  return (
    <DrawerPanel title="角色">
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

export function MemoryPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [view, setView] = useState<MemoryView>(EMPTY_MEMORY)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<MemoryItem | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmForget, setConfirmForget] = useState(false)

  const refresh = (category = view.selectedCategory || 'all', search = query) =>
    requestCommand('get_memory_view', { category, query: search })
      .then(data => setView((data as any).view ?? EMPTY_MEMORY))

  useEffect(() => {
    void refresh('all', '')
  }, [])

  const choose = (item: MemoryItem) => {
    setSelected(item)
    setDraft(item.summary)
    setConfirmForget(false)
  }

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
            <button type="button" key={item.ref} onClick={() => choose(item)}>
              <span>{item.pinned ? '置顶 · ' : ''}{categoryLabel(item.category)}</span>
              <strong>{item.summary}</strong>
              <small>{formatDate(item.updatedAt)}</small>
            </button>
          ))}
        </div>
        {selected && (
          <section className="memory-editor">
            <span className="eyebrow">记忆详情</span>
            <textarea value={draft} onChange={event => setDraft(event.target.value)} />
            <dl className="memory-context">
              <div><dt>形成于</dt><dd>{formatDate(selected.formedAt)}</dd></div>
              <div><dt>最近使用</dt><dd>{formatDate(selected.lastUsedAt)}</dd></div>
              <div><dt>形成原因</dt><dd>{selected.formationReason || '从相关对话中形成'}</dd></div>
            </dl>
            <div className="memory-editor-actions">
              <button type="button" onClick={() => void requestCommand(
                'update_memory_view', { ref: selected.ref, content: draft }
              )}>保存修改</button>
              <button type="button" onClick={() => void requestCommand(
                'update_memory_view', { ref: selected.ref, pinned: !selected.pinned }
              )}>{selected.pinned ? '取消置顶' : '置顶'}</button>
              {!confirmForget ? (
                <button type="button" onClick={() => setConfirmForget(true)}>遗忘…</button>
              ) : (
                <button type="button" className="danger" onClick={() =>
                  void requestCommand('forget_memory_view', { ref: selected.ref })
                }>确认遗忘</button>
              )}
            </div>
          </section>
        )}
      </div>
    </DrawerPanel>
  )
}

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

export function CapabilityPanel({ requestCommand }: { requestCommand: RequestCommand }) {
  const [items, setItems] = useState<CapabilityItem[]>([])
  const refresh = () => requestCommand('get_capability_view', {})
    .then(data => setItems((data as any).view?.items ?? []))
  useEffect(() => {
    void refresh()
  }, [])
  return (
    <DrawerPanel title="能力">
      <div className="capability-view">
        {items.length === 0 && <EmptyState>当前没有可用的外部能力。</EmptyState>}
        {items.map(item => (
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
              className={item.status === 'available' ? 'is-active' : ''}
              onClick={() => void requestCommand('set_tool_enabled', {
                name: item.name,
                enabled: item.status !== 'available',
              })}
            >{item.status === 'available' ? '已开启' : '已关闭'}</button>
          </article>
        ))}
      </div>
    </DrawerPanel>
  )
}

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

function categoryLabel(category: string) {
  return ({
    about_user: '关于你',
    shared: '共同经历',
    character: '角色自身',
    preferences: '偏好习惯',
    goals: '持续目标',
  } as Record<string, string>)[category] ?? '记忆'
}

function formatDate(value?: string) {
  if (!value) return '尚未使用'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
