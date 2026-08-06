import { useCallback, useEffect, useState } from 'react'
import { FolderOpen, RefreshCw, Upload } from 'lucide-react'

import {
  buildCharacterImportPayload,
  readCharacterCatalog,
  type CharacterDescriptor,
  type CharacterImportForm,
} from './character-catalog'

type Props = {
  requestCommand: (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>
  onActivate: (character: CharacterDescriptor) => Promise<void>
}

const EMPTY_FORM: CharacterImportForm = {
  id: '', name: '', persona: '', replyLanguage: 'zh',
  promptLanguage: 'zh', promptText: '', live2dDirectory: '',
  referenceAudio: '', t2sModel: '', vitsModel: '',
}

const ASSET_FIELDS = [
  ['live2dDirectory', 'live2d_directory', 'Live2D 模型目录'],
  ['referenceAudio', 'reference_audio', '声线参考音频'],
  ['t2sModel', 't2s_model', 'GPT 模型（.ckpt）'],
  ['vitsModel', 'vits_model', 'SoVITS 模型（.pth）'],
] as const

export function CharacterManagerPanel({ requestCommand, onActivate }: Props) {
  const [characters, setCharacters] = useState<CharacterDescriptor[]>([])
  const [activeId, setActiveId] = useState('')
  const [form, setForm] = useState<CharacterImportForm>(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const catalog = readCharacterCatalog(await requestCommand('get_character_catalog', {}))
      setCharacters(catalog.characters)
      setActiveId(catalog.activeCharacterId)
      setMessage('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '角色目录加载失败')
    } finally {
      setLoading(false)
    }
  }, [requestCommand])

  useEffect(() => { void refresh() }, [refresh])

  const update = <K extends keyof CharacterImportForm>(key: K, value: CharacterImportForm[K]) => {
    setForm(current => ({ ...current, [key]: value }))
  }

  const selectAsset = async (
    field: keyof CharacterImportForm,
    kind: string,
  ) => {
    const selected = await window.electronAPI?.selectCharacterAsset?.(kind)
    if (selected) update(field, selected)
  }

  const activate = async (character: CharacterDescriptor) => {
    if (character.id === activeId) return
    setMessage(`正在切换到 ${character.name}…`)
    try {
      await onActivate(character)
      setActiveId(character.id)
      setMessage(`已切换到 ${character.name}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '角色切换失败')
      throw error
    }
  }

  const submit = async () => {
    setImporting(true)
    setMessage('正在校验并复制完整 Live2D 与语音资源，请勿关闭程序…')
    try {
      const response = await requestCommand(
        'create_character',
        buildCharacterImportPayload(form),
      )
      const raw = response.character as Record<string, unknown> | undefined
      if (!raw?.id) throw new Error('导入完成但未返回角色信息')
      const character: CharacterDescriptor = {
        id: String(raw.id), name: String(raw.name || raw.id),
        replyLanguage: String(raw.reply_language || form.replyLanguage),
        live2dModel: String(raw.live2d_model || raw.id),
        voiceConfigured: raw.voice_configured === true,
      }
      setCharacters(current => [...current.filter(item => item.id !== character.id), character])
      try {
        await activate(character)
      } catch (error) {
        const detail = error instanceof Error ? error.message : '未知错误'
        setMessage(`角色 ${character.name} 已导入，但启用失败：${detail}`)
        return
      }
      setForm(EMPTY_FORM)
      setShowImport(false)
      setMessage(`角色 ${character.name} 已完整导入并启用`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '完整角色导入失败')
    } finally {
      setImporting(false)
    }
  }

  const complete = Boolean(
    form.id.trim() && form.name.trim() && form.persona.trim()
    && form.promptText.trim() && form.live2dDirectory.trim()
    && form.referenceAudio.trim() && form.t2sModel.trim() && form.vitsModel.trim(),
  )

  return (
    <section className="character-manager">
      <header className="character-manager-header">
        <div>
          <h2>角色资源库</h2>
          <p>身份、回复语言、Live2D 和声线均按角色独立保存。</p>
        </div>
        <button className="icon-button" onClick={() => void refresh()} title="刷新角色目录">
          <RefreshCw size={16} />
        </button>
      </header>

      <div className="character-card-list">
        {loading && <p className="muted">正在读取磁盘角色目录…</p>}
        {!loading && characters.length === 0 && <p className="muted">尚未发现可用角色。</p>}
        {characters.map(character => (
          <button
            key={character.id}
            className={`character-library-card ${character.id === activeId ? 'is-active' : ''}`}
            onClick={() => { void activate(character).catch(() => {}) }}
          >
            <span><strong>{character.name}</strong><small>{character.id}</small></span>
            <span className="character-library-meta">
              {character.replyLanguage.toUpperCase()} · Live2D · {character.voiceConfigured ? '声线就绪' : '声线缺失'}
            </span>
            <em>{character.id === activeId ? '使用中' : '切换'}</em>
          </button>
        ))}
      </div>

      <button className="character-import-toggle" onClick={() => setShowImport(value => !value)}>
        <Upload size={16} /> {showImport ? '收起导入向导' : '导入完整 Live2D＋语音角色'}
      </button>

      {showImport && (
        <div className="character-import-form">
          <h3>基础信息</h3>
          <div className="character-form-grid">
            <label>角色 ID<input value={form.id} onChange={event => update('id', event.target.value)} placeholder="例如 lantern（小写英文）" /></label>
            <label>显示名称<input value={form.name} onChange={event => update('name', event.target.value)} placeholder="角色名称" /></label>
            <label>回复语言<select value={form.replyLanguage} onChange={event => update('replyLanguage', event.target.value)}><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="yue">粤语</option></select></label>
            <label>参考音频语言<select value={form.promptLanguage} onChange={event => update('promptLanguage', event.target.value)}><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="yue">粤语</option></select></label>
          </div>
          <label>角色设定<textarea value={form.persona} onChange={event => update('persona', event.target.value)} placeholder="身份、语气、背景与行为边界" /></label>
          <label>参考音频原文<textarea value={form.promptText} onChange={event => update('promptText', event.target.value)} placeholder="必须与参考音频实际内容一致" /></label>

          <h3>完整资源</h3>
          {ASSET_FIELDS.map(([field, kind, label]) => (
            <label className="character-asset-field" key={field}>
              <span>{label}</span>
              <div><input value={form[field]} onChange={event => update(field, event.target.value)} placeholder="可粘贴绝对路径" /><button type="button" onClick={() => void selectAsset(field, kind)}><FolderOpen size={15} />选择</button></div>
            </label>
          ))}
          <p className="character-import-note">Live2D 目录需包含一个顶层 .model3.json 及其引用资源；导入会复制资源并验证，失败不会留下半成品。</p>
          <button className="character-import-submit" disabled={!complete || importing} onClick={() => void submit()}>
            {importing ? '正在完整导入…' : '校验、导入并启用角色'}
          </button>
        </div>
      )}
      {message && <p className="character-manager-message" role="status">{message}</p>}
    </section>
  )
}
