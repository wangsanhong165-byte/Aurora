import { ChevronDown, FilePenLine, LockKeyhole, RefreshCw, RotateCcw, Save } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { eventBus } from '../core/event-bus'
import { DrawerPanel } from './DrawerPanel'
import {
  buildPromptConfigPayload,
  describePromptMessage,
  formatPromptContent,
  promptConfigsEqual,
  promptMessageStats,
  promptSourceEditorSeed,
  promptSourcePreview,
  type PromptConfigView,
  type PromptSourceMode,
  type PromptSourceView,
} from './prompt-view'

type RequestCommand = (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>

const MAX_PROMPT_CHARS = 12_000

type PromptMessage = {
  role: string
  content?: unknown
  source_id?: string
  tool_call_id?: string
  tool_calls?: unknown[]
}

type PromptView = {
  available: boolean
  character_id: string
  snapshot_character_id: string
  turn_id: string
  created_at: number
  messages: PromptMessage[]
  context_budget: Record<string, unknown>
}

type PromptStatus =
  | { kind: 'idle'; text: string }
  | { kind: 'saving'; text: string }
  | { kind: 'saved'; text: string }
  | { kind: 'error'; text: string }

type PromptDisplayMode = 'structured' | 'raw'
type PromptPanelTab = 'config' | 'request'

function parsePromptView(data: Record<string, unknown>, characterId: string): PromptView {
  return {
    available: Boolean(data.available),
    character_id: String(data.character_id || characterId),
    snapshot_character_id: String(data.snapshot_character_id ?? ''),
    turn_id: String(data.turn_id ?? ''),
    created_at: Number(data.created_at ?? 0),
    messages: Array.isArray(data.messages) ? data.messages as PromptMessage[] : [],
    context_budget: data.context_budget && typeof data.context_budget === 'object'
      ? data.context_budget as Record<string, unknown>
      : {},
  }
}

function parsePromptConfig(data: Record<string, unknown>, characterId: string): PromptConfigView {
  const sources = Array.isArray(data.sources) ? data.sources : []
  return {
    character_id: String(data.character_id || characterId),
    addition: String(data.addition ?? ''),
    sources: sources
      .filter((source): source is Record<string, unknown> => Boolean(source && typeof source === 'object'))
      .map(source => ({
        id: String(source.id ?? ''),
        title: String(source.title ?? source.id ?? ''),
        description: String(source.description ?? ''),
        dynamic: Boolean(source.dynamic),
        editable: Boolean(source.editable),
        mode: (['default', 'replace', 'disabled'].includes(String(source.mode))
          ? String(source.mode)
          : 'default') as PromptSourceMode,
        content: String(source.content ?? ''),
        default_content: String(source.default_content ?? ''),
        last_content: String(source.last_content ?? ''),
      }))
      .filter(source => source.id),
  }
}

function modeLabel(source: PromptSourceView): string {
  if (!source.editable) return '运行必需'
  return ({ default: '使用默认', replace: '自定义替换', disabled: '已关闭' } as const)[source.mode]
}

export function PromptPanel({
  requestCommand,
  activeCharacterId,
}: {
  requestCommand: RequestCommand
  activeCharacterId: string
}) {
  const [panelTab, setPanelTab] = useState<PromptPanelTab>('config')
  const [displayMode, setDisplayMode] = useState<PromptDisplayMode>('structured')
  const [view, setView] = useState<PromptView | null>(null)
  const [savedConfig, setSavedConfig] = useState<PromptConfigView | null>(null)
  const [draft, setDraft] = useState<PromptConfigView | null>(null)
  const [loadedCharacterId, setLoadedCharacterId] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [status, setStatus] = useState<PromptStatus>({ kind: 'idle', text: '' })

  const requestSequence = useRef(0)
  const requestCommandRef = useRef(requestCommand)
  const draftCache = useRef(new Map<string, PromptConfigView>())
  const savedConfigRef = useRef<PromptConfigView | null>(null)
  const draftRef = useRef<PromptConfigView | null>(null)
  const loadedCharacterRef = useRef('')

  useEffect(() => { requestCommandRef.current = requestCommand }, [requestCommand])
  useEffect(() => { savedConfigRef.current = savedConfig }, [savedConfig])
  useEffect(() => { draftRef.current = draft }, [draft])
  useEffect(() => { loadedCharacterRef.current = loadedCharacterId }, [loadedCharacterId])

  const loadCharacter = useCallback(async (characterId: string, preserveDraft = true) => {
    const targetId = characterId || 'monika'
    const previousId = loadedCharacterRef.current
    if (
      preserveDraft
      && previousId
      && draftRef.current
      && !promptConfigsEqual(savedConfigRef.current, draftRef.current)
    ) {
      draftCache.current.set(previousId, draftRef.current)
    }

    const sequence = ++requestSequence.current
    setRefreshing(true)
    try {
      const [configData, viewData] = await Promise.all([
        requestCommandRef.current('get_prompt_config', { character_id: targetId }),
        requestCommandRef.current('get_prompt_view', { character_id: targetId }),
      ])
      if (sequence !== requestSequence.current) return

      const serverConfig = parsePromptConfig(configData, targetId)
      const cachedDraft = draftCache.current.get(targetId)
      setSavedConfig(serverConfig)
      setDraft(cachedDraft ?? serverConfig)
      setView(parsePromptView(viewData, targetId))
      setLoadedCharacterId(targetId)
      setStatus(cachedDraft
        ? { kind: 'idle', text: '已恢复该角色尚未保存的草稿。' }
        : { kind: 'idle', text: '' })
    } catch {
      if (sequence === requestSequence.current) {
        setStatus({ kind: 'error', text: '读取失败，请确认运行时服务已更新并重试。' })
      }
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadCharacter(activeCharacterId || 'monika')
  }, [activeCharacterId, loadCharacter])

  useEffect(() => {
    const unsubTurn = eventBus.on('runtime:turn.completed', () => {
      void loadCharacter(loadedCharacterRef.current || activeCharacterId || 'monika')
    })
    const unsubConnection = eventBus.on('connection:change', ({ connected }) => {
      if (connected) void loadCharacter(activeCharacterId || 'monika')
    })
    return () => {
      unsubTurn()
      unsubConnection()
    }
  }, [activeCharacterId, loadCharacter])

  const dirty = !promptConfigsEqual(savedConfig, draft)
  const characterReady = Boolean(
    draft && loadedCharacterId && loadedCharacterId === (activeCharacterId || 'monika'),
  )

  const updateSource = (sourceId: string, update: Partial<Pick<PromptSourceView, 'mode' | 'content'>>) => {
    setDraft(current => current ? {
      ...current,
      sources: current.sources.map(source => source.id === sourceId
        ? { ...source, ...update }
        : source),
    } : current)
    if (status.kind !== 'idle') setStatus({ kind: 'idle', text: '' })
  }

  const setSourceMode = (source: PromptSourceView, mode: PromptSourceMode) => {
    updateSource(source.id, {
      mode,
      content: mode === 'replace' ? promptSourceEditorSeed(source) : '',
    })
  }

  const save = async () => {
    if (!draft || !characterReady) return
    setStatus({ kind: 'saving', text: '保存中…' })
    try {
      const data = await requestCommand('set_prompt_config', buildPromptConfigPayload(draft))
      const nextConfig = parsePromptConfig(data, draft.character_id)
      draftCache.current.delete(draft.character_id)
      setSavedConfig(nextConfig)
      setDraft(nextConfig)
      setStatus({ kind: 'saved', text: '已保存；下一轮请求按此配置生成。' })
    } catch {
      setStatus({ kind: 'error', text: '保存失败；请检查自定义替换内容后重试。' })
    }
  }

  const restoreAllDefaults = () => {
    setDraft(current => current ? {
      ...current,
      addition: '',
      sources: current.sources.map(source => source.editable
        ? { ...source, mode: 'default', content: '' }
        : source),
    } : current)
    setStatus({ kind: 'idle', text: '已在草稿中恢复默认，保存后生效。' })
  }

  const stats = promptMessageStats(view?.messages ?? [])

  return (
    <DrawerPanel title="提示词" action={
      <button
        type="button"
        className="drawer-text-action"
        disabled={refreshing}
        onClick={() => void loadCharacter(activeCharacterId || 'monika')}
      >
        <RefreshCw size={13} strokeWidth={1.75} aria-hidden="true" />
        {refreshing ? '更新中…' : '刷新'}
      </button>
    }>
      <div className="prompt-panel">
        <div className="prompt-panel-tabs" role="tablist" aria-label="提示词功能">
          <button
            type="button"
            role="tab"
            aria-selected={panelTab === 'config'}
            className={panelTab === 'config' ? 'is-active' : ''}
            onClick={() => setPanelTab('config')}
          >
            提示词配置
            {dirty && <span className="prompt-unsaved-dot" aria-label="有未保存修改" />}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={panelTab === 'request'}
            className={panelTab === 'request' ? 'is-active' : ''}
            onClick={() => setPanelTab('request')}
          >
            请求记录
          </button>
        </div>

        {panelTab === 'config' ? (
          <section className="prompt-config-view" aria-label="提示词配置">
            <div className="prompt-panel-intro">
              <FilePenLine className="prompt-panel-icon" size={18} strokeWidth={1.75} aria-hidden="true" />
              <div>
                <strong>角色提示词配置</strong>
                <p>控制 system 上下文的来源；用户输入不会出现在这里。</p>
              </div>
            </div>

            <div className="prompt-panel-meta prompt-config-character">
              <span>当前角色：{loadedCharacterId || activeCharacterId || '读取中…'}</span>
              <span>{dirty ? '有未保存修改' : '已与磁盘同步'}</span>
            </div>

            {draft ? (
              <div className="prompt-source-list">
                {draft.sources.map(source => (
                  <details className={`prompt-source-card is-${source.mode}`} key={source.id}>
                    <summary>
                      <span className="prompt-source-heading">
                        <strong>{source.title}</strong>
                        <span>{source.description}</span>
                      </span>
                      <span className={`prompt-source-mode is-${source.mode}`}>{modeLabel(source)}</span>
                      <ChevronDown size={14} strokeWidth={1.75} aria-hidden="true" />
                    </summary>

                    <div className="prompt-source-body">
                      {source.editable ? (
                        <div className="prompt-source-mode-picker" aria-label={`${source.title}处理方式`}>
                          {([
                            ['default', '使用默认'],
                            ['replace', '自定义替换'],
                            ['disabled', '关闭'],
                          ] as Array<[PromptSourceMode, string]>).map(([mode, label]) => (
                            <button
                              type="button"
                              key={mode}
                              className={source.mode === mode ? 'is-active' : ''}
                              aria-pressed={source.mode === mode}
                              onClick={() => setSourceMode(source, mode)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="prompt-source-required">
                          <LockKeyhole size={13} strokeWidth={1.75} aria-hidden="true" />
                          此协议维持结构化回复、动作和语音链路，因此只读。
                        </p>
                      )}

                      {source.mode === 'replace' && (
                        <textarea
                          className="prompt-source-textarea"
                          value={source.content}
                          maxLength={MAX_PROMPT_CHARS}
                          onChange={event => updateSource(source.id, { content: event.target.value })}
                          placeholder={`输入用于完全替换“${source.title}”的内容…`}
                          aria-label={`${source.title}自定义替换内容`}
                        />
                      )}

                      {source.mode === 'disabled' ? (
                        <p className="prompt-source-disabled-note">下一轮不会向模型发送这一来源。</p>
                      ) : promptSourcePreview(source) ? (
                        <div className="prompt-source-preview">
                          <span>{promptSourcePreview(source)?.label}</span>
                          <pre>{promptSourcePreview(source)?.content}</pre>
                        </div>
                      ) : (
                        <p className="prompt-source-disabled-note">
                          {source.dynamic ? '该内容会在下一轮按当前状态动态生成。' : '该角色尚无可展示的请求记录。'}
                        </p>
                      )}
                    </div>
                  </details>
                ))}

                <section className="prompt-addition-editor">
                  <div className="prompt-panel-section-heading">
                    <strong>附加提示词</strong>
                    <span>可选 · 当前角色独立保存</span>
                  </div>
                  <p className="prompt-panel-section-note">
                    在以上来源之后额外追加一条 system 消息；留空则不追加。
                  </p>
                  <textarea
                    value={draft.addition}
                    maxLength={MAX_PROMPT_CHARS}
                    disabled={loading || status.kind === 'saving'}
                    onChange={event => {
                      const addition = event.target.value
                      setDraft(current => current ? { ...current, addition } : current)
                      if (status.kind !== 'idle') setStatus({ kind: 'idle', text: '' })
                    }}
                    placeholder="输入额外角色语气、行为偏好或项目约束…"
                    aria-label="附加提示词"
                  />
                  <div className="prompt-panel-meta">
                    <span>切换角色时自动加载对应配置</span>
                    <span>{draft.addition.length.toLocaleString()} / {MAX_PROMPT_CHARS.toLocaleString()}</span>
                  </div>
                </section>

                <div className="prompt-config-actions">
                  <button
                    type="button"
                    className="prompt-save-button"
                    disabled={!dirty || !characterReady || status.kind === 'saving'}
                    onClick={() => void save()}
                  >
                    <Save size={14} strokeWidth={1.75} aria-hidden="true" />
                    保存当前角色配置
                  </button>
                  <button
                    type="button"
                    className="prompt-reset-button"
                    disabled={!draft.sources.some(source => source.editable && source.mode !== 'default') && !draft.addition}
                    onClick={restoreAllDefaults}
                  >
                    <RotateCcw size={13} strokeWidth={1.75} aria-hidden="true" />
                    全部恢复默认
                  </button>
                </div>
                {status.text && <p className={`prompt-status is-${status.kind}`}>{status.text}</p>}
              </div>
            ) : (
              <p className="prompt-panel-empty">正在读取当前角色的提示词配置…</p>
            )}
          </section>
        ) : (
          <section className="prompt-request-view" aria-label="上一次 LLM 请求记录">
            <div className="prompt-panel-intro">
              <FilePenLine className="prompt-panel-icon" size={18} strokeWidth={1.75} aria-hidden="true" />
              <div>
                <strong>上一次 LLM 请求记录</strong>
                <p>这是只读审计记录，包含 system 上下文和本轮用户输入。</p>
              </div>
            </div>

            <div className="prompt-panel-meta">
              <span>记录角色：{view?.snapshot_character_id || loadedCharacterId || '—'}</span>
              <span>{view?.available
                ? `${view.messages.length} 条消息 · 估算 ${String(view.context_budget.estimated_tokens ?? '—')} tokens`
                : '该角色尚无请求记录'}</span>
            </div>

            {view?.available && view.messages.length > 0 ? (
              <>
                <div className="prompt-view-toolbar">
                  <span className="prompt-view-summary">
                    {stats.context} 项 system 上下文 · {stats.user} 条本轮输入
                    {stats.other > 0 ? ` · ${stats.other} 条历史/工具消息` : ''}
                  </span>
                  <div className="prompt-view-toggle" aria-label="请求记录显示方式">
                    <button
                      type="button"
                      className={displayMode === 'structured' ? 'is-active' : ''}
                      aria-pressed={displayMode === 'structured'}
                      onClick={() => setDisplayMode('structured')}
                    >
                      结构
                    </button>
                    <button
                      type="button"
                      className={displayMode === 'raw' ? 'is-active' : ''}
                      aria-pressed={displayMode === 'raw'}
                      onClick={() => setDisplayMode('raw')}
                    >
                      原始
                    </button>
                  </div>
                </div>

                <p className="prompt-snapshot-note">请求记录不会随配置编辑改变；发送新消息后生成新的记录。</p>

                {displayMode === 'structured' ? (
                  <div className="prompt-message-list is-structured" aria-label="按用途整理的 LLM 请求消息">
                    {view.messages.map((message, index) => {
                      const descriptor = describePromptMessage(message)
                      return (
                        <details
                          className={`prompt-message-details is-${descriptor.kind}`}
                          key={`${message.role}-${index}`}
                          open={descriptor.defaultOpen}
                        >
                          <summary>
                            <span className="prompt-message-index">{String(index + 1).padStart(2, '0')}</span>
                            <span className="prompt-message-title">
                              <strong>{descriptor.title}</strong>
                              <span>{descriptor.summary}</span>
                            </span>
                            <span className="prompt-message-badge">{descriptor.badge}</span>
                            <ChevronDown className="prompt-message-chevron" size={14} strokeWidth={1.75} aria-hidden="true" />
                          </summary>
                          <pre className="prompt-message-content">{formatPromptContent(message.content)}</pre>
                          {message.tool_calls && (
                            <pre className="prompt-message-content prompt-message-tools">{formatPromptContent(message.tool_calls)}</pre>
                          )}
                        </details>
                      )
                    })}
                  </div>
                ) : (
                  <div className="prompt-message-list is-raw" aria-label="原始 LLM 请求消息">
                    {view.messages.map((message, index) => (
                      <article className={`prompt-message-card is-${message.role}`} key={`${message.role}-${index}`}>
                        <div className="prompt-message-heading">
                          <span>消息 {String(index + 1).padStart(2, '0')}</span>
                          <span>{message.role}</span>
                        </div>
                        <pre className="prompt-message-content">{formatPromptContent(message.content)}</pre>
                        {message.tool_calls && (
                          <pre className="prompt-message-content prompt-message-tools">{formatPromptContent(message.tool_calls)}</pre>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="prompt-panel-empty">该角色尚未产生 LLM 请求。发送一条消息后，这里会显示完整请求记录。</p>
            )}
          </section>
        )}
      </div>
    </DrawerPanel>
  )
}
