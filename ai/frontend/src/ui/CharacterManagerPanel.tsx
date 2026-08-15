import { useCallback, useEffect, useRef, useState } from 'react'
import { FolderOpen, Pencil, RefreshCw, Trash2, Upload } from 'lucide-react'

import {
  buildCharacterPayload,
  buildCharacterUpdatePayload,
  buildVoicePayload,
  emptyPersonalityProfile,
  readCharacterCatalog,
  readCharacterDetail,
  readModelCatalog,
  readVoiceCatalog,
  type CharacterDetail,
  type CharacterDescriptor,
  type CharacterForm,
  type ModelDescriptor,
  type PersonalityProfile,
  type VoiceDescriptor,
  type VoiceForm,
} from './character-catalog'

type Props = {
  requestCommand: (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>
  onActivate: (character: CharacterDescriptor, runtimeAlreadySwitched?: boolean) => Promise<void>
}

type Tab = 'characters' | 'voices' | 'models'

const EMPTY_CHARACTER: CharacterForm = {
  id: '', name: '', persona: '', replyLanguage: 'zh', modelId: '', voiceId: '',
  personalityProfile: emptyPersonalityProfile(),
}
const EMPTY_VOICE: VoiceForm = {
  id: '', name: '', promptLanguage: 'zh', promptText: '',
  referenceAudio: '', t2sModel: '', vitsModel: '',
}

const VOICE_ASSET_FIELDS = [
  ['referenceAudio', 'reference_audio', '声线参考音频'],
  ['t2sModel', 't2s_model', 'GPT 模型（.ckpt）'],
  ['vitsModel', 'vits_model', 'SoVITS 模型（.pth）'],
] as const

export function CharacterManagerPanel({ requestCommand, onActivate }: Props) {
  const [tab, setTab] = useState<Tab>('characters')
  const [characters, setCharacters] = useState<CharacterDescriptor[]>([])
  const [voices, setVoices] = useState<VoiceDescriptor[]>([])
  const [models, setModels] = useState<ModelDescriptor[]>([])
  const [activeId, setActiveId] = useState('')
  const [characterForm, setCharacterForm] = useState<CharacterForm>(EMPTY_CHARACTER)
  const [voiceForm, setVoiceForm] = useState<VoiceForm>(EMPTY_VOICE)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [showCharacterForm, setShowCharacterForm] = useState(false)
  const [showVoiceForm, setShowVoiceForm] = useState(false)
  const [editingCharacter, setEditingCharacter] = useState<CharacterDetail | null>(null)
  const [message, setMessage] = useState('')

  // requestCommand is an inline prop that the provider recreates on every
  // render; route it through a ref so refresh/useEffect stay stable and the
  // panel does not enter an infinite refresh loop.
  const requestRef = useRef(requestCommand)
  requestRef.current = requestCommand

  const refresh = useCallback(async () => {
    setLoading(true)
    setMessage('')
    try {
      const [charactersRaw, voicesRaw, modelsRaw] = await Promise.all([
        requestRef.current('get_character_catalog', {}),
        requestRef.current('get_voice_catalog', {}),
        requestRef.current('get_model_catalog', {}),
      ])
      const catalog = readCharacterCatalog(charactersRaw)
      setCharacters(catalog.characters)
      setActiveId(catalog.activeCharacterId)
      setVoices(readVoiceCatalog(voicesRaw))
      setModels(readModelCatalog(modelsRaw))
      // Refresh the model snapshot so newly registered models are attachable
      // without a full page reload.
      try {
        const modelInfoResponse = await fetch('/api/model-info')
        if (modelInfoResponse.ok) {
          ;(window as any).__INITIAL_MODEL_INFO__ = await modelInfoResponse.json()
        }
      } catch { /* keep the existing snapshot */ }
      return true
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '资源库加载失败')
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const run = async () => {
      if (cancelled) return
      const ok = await refresh()
      if (!ok && attempts++ < 15 && !cancelled) {
        setTimeout(run, 700)
      }
    }
    void run()
    return () => { cancelled = true }
  }, [refresh])

  const updateCharacter = <K extends keyof CharacterForm>(key: K, value: CharacterForm[K]) => {
    setCharacterForm(current => ({ ...current, [key]: value }))
  }
  const updateVoice = <K extends keyof VoiceForm>(key: K, value: VoiceForm[K]) => {
    setVoiceForm(current => ({ ...current, [key]: value }))
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
  const updatePersonality = (profile: PersonalityProfile) => {
    updateCharacter('personalityProfile', profile)
  }
  const listValue = (value: string) => value
    .split(/\r?\n|，|,/).map(item => item.trim()).filter(Boolean)

  const closeCharacterForm = () => {
    setCharacterForm(EMPTY_CHARACTER)
    setEditingCharacter(null)
    setShowCharacterForm(false)
    setMessage('')
  }

  const toggleCreateCharacter = () => {
    if (showCharacterForm) {
      closeCharacterForm()
      return
    }
    setEditingCharacter(null)
    setCharacterForm(EMPTY_CHARACTER)
    setShowCharacterForm(true)
  }

  const editCharacter = async (character: CharacterDescriptor) => {
    setBusy(true)
    setMessage(`正在读取 ${character.name} 的角色卡…`)
    try {
      const response = await requestRef.current('get_character_detail', {
        character_id: character.id,
      })
      const detail = readCharacterDetail(response)
      setEditingCharacter(detail)
      setCharacterForm({
        id: detail.id,
        name: detail.name,
        persona: detail.persona,
        replyLanguage: detail.replyLanguage,
        modelId: detail.modelId,
        voiceId: detail.voiceId,
        personalityProfile: detail.personalityProfile,
      })
      setShowCharacterForm(true)
      setMessage(`正在编辑 ${detail.name}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '角色详情读取失败')
    } finally {
      setBusy(false)
    }
  }

  const removeCharacter = async (character: CharacterDescriptor) => {
    if (characters.length <= 1) {
      setMessage('至少需要保留一个角色')
      return
    }
    if (!window.confirm(`删除角色“${character.name}”？角色提示词、对话记忆和状态会一并删除；共享模型与声线会保留。`)) {
      return
    }
    setBusy(true)
    setMessage(`正在删除 ${character.name}…`)
    try {
      const response = await requestRef.current('delete_character', { character_id: character.id })
      const nextActive = String(response.active_character_id || '')
      setCharacters(current => current.filter(item => item.id !== character.id))
      if (nextActive) setActiveId(nextActive)
      let syncWarning = ''
      if (character.id === activeId && nextActive) {
        const fallback = characters.find(item => item.id === nextActive)
        if (fallback) {
          try {
            // The backend has already switched atomically. Re-applying the
            // active role here synchronizes the renderer's model/settings.
            await onActivate(fallback, true)
          } catch (error) {
            syncWarning = error instanceof Error ? error.message : String(error)
          }
        }
      }
      await refresh()
      setMessage(
        syncWarning
          ? `角色 ${character.name} 已删除，但界面同步失败：${syncWarning}`
          : `角色 ${character.name} 已删除，共享模型与声线已保留`,
      )
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '角色删除失败')
    } finally {
      setBusy(false)
    }
  }

  const selectAsset = async (
    field: keyof VoiceForm,
    kind: string,
  ) => {
    const selected = await window.electronAPI?.selectCharacterAsset?.(kind)
    if (selected) updateVoice(field, selected)
  }

  const submitCharacter = async () => {
    setBusy(true)
    setMessage(editingCharacter ? '正在保存角色卡…' : '正在创建角色…')
    try {
      if (editingCharacter) {
        const response = await requestRef.current('update_character', {
          character_id: editingCharacter.id,
          ...buildCharacterUpdatePayload(
            characterForm,
            editingCharacter.resourceReferencesEditable,
          ),
        })
        const detail = readCharacterDetail(response)
        const character: CharacterDescriptor = detail
        setCharacters(current => current.map(item => (
          item.id === character.id ? character : item
        )))
        let syncWarning = ''
        if (character.id === activeId && response.runtime_reloaded === true) {
          try {
            await onActivate(character, true)
          } catch (error) {
            syncWarning = error instanceof Error ? error.message : String(error)
          }
        }
        closeCharacterForm()
        await refresh()
        setMessage(syncWarning
          ? `角色 ${character.name} 已保存，但界面同步失败：${syncWarning}`
          : `角色 ${character.name} 已保存`)
        return
      }

      const response = await requestRef.current(
        'create_character',
        buildCharacterPayload(characterForm),
      )
      const raw = response.character as Record<string, unknown> | undefined
      if (!raw?.id) throw new Error('创建完成但未返回角色信息')
      const character: CharacterDescriptor = {
        id: String(raw.id), name: String(raw.name || raw.id),
        replyLanguage: String(raw.reply_language || characterForm.replyLanguage),
        live2dModel: String(raw.live2d_model || ''),
        voiceConfigured: raw.voice_configured === true,
      }
      setCharacters(current => [...current.filter(item => item.id !== character.id), character])
      await activate(character)
      closeCharacterForm()
      setMessage(`角色 ${character.name} 已创建并启用`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '角色创建失败')
    } finally {
      setBusy(false)
    }
  }

  const submitVoice = async () => {
    setBusy(true)
    setMessage('正在添加声线…')
    try {
      const response = await requestRef.current('add_voice', buildVoicePayload(voiceForm))
      const raw = response.voice as Record<string, unknown> | undefined
      if (!raw?.id) throw new Error('添加完成但未返回声线信息')
      setVoices(current => [...current.filter(item => item.id !== raw.id), {
        id: String(raw.id), name: String(raw.name || raw.id),
        promptText: String(raw.prompt_text || ''), promptLang: String(raw.prompt_lang || 'en'),
        configured: raw.configured === true,
      }])
      setVoiceForm(EMPTY_VOICE)
      setShowVoiceForm(false)
      setMessage(`声线 ${raw.name || raw.id} 已添加`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '声线添加失败')
    } finally {
      setBusy(false)
    }
  }

  const registerAllModels = async () => {
    setBusy(true)
    setMessage('正在补齐模型注册项…')
    try {
      const pending = models.filter(model => !model.profile)
      for (const model of pending) {
        await requestRef.current('register_model', { model_id: model.id })
      }
      setMessage(`已注册 ${pending.length} 个模型`)
      await refresh()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '模型注册失败')
    } finally {
      setBusy(false)
    }
  }

  const personality = characterForm.personalityProfile ?? emptyPersonalityProfile()
  const characterComplete = Boolean(
    characterForm.id.trim() && characterForm.name.trim() && characterForm.persona.trim()
    && (
      editingCharacter && !editingCharacter.resourceReferencesEditable
        ? true
        : characterForm.modelId && characterForm.voiceId
    ),
  )
  const voiceComplete = Boolean(
    voiceForm.id.trim() && voiceForm.name.trim() && voiceForm.promptText.trim()
    && voiceForm.referenceAudio.trim() && voiceForm.t2sModel.trim() && voiceForm.vitsModel.trim(),
  )

  return (
    <section className="character-manager">
      <header className="character-manager-header">
        <div>
          <h2>角色资源库</h2>
          <p>模型、声线在系统层自由添加；角色只引用，不复制资源。</p>
        </div>
        <button className="icon-button" onClick={() => void refresh()} title="刷新目录">
          <RefreshCw size={16} />
        </button>
      </header>

      <div className="prompt-panel-tabs">
        <button className={tab === 'characters' ? 'is-active' : ''} onClick={() => setTab('characters')}>角色</button>
        <button className={tab === 'voices' ? 'is-active' : ''} onClick={() => setTab('voices')}>声线</button>
        <button className={tab === 'models' ? 'is-active' : ''} onClick={() => setTab('models')}>模型</button>
      </div>

      {tab === 'characters' && (
        <>
          <div className="character-card-list">
            {loading && <p className="muted">正在读取磁盘角色目录…</p>}
            {!loading && characters.length === 0 && <p className="muted">尚未发现可用角色。</p>}
            {characters.map(character => (
              <div className="character-library-row" key={character.id}>
                <button
                  className={`character-library-card ${character.id === activeId ? 'is-active' : ''}`}
                  onClick={() => { void activate(character).catch(() => {}) }}
                >
                  <span><strong>{character.name}</strong><small>{character.id}</small></span>
                  <span className="character-library-meta">
                    {character.replyLanguage.toUpperCase()} · {character.live2dModel} · {character.voiceConfigured ? '声线就绪' : '声线缺失'}
                  </span>
                  <em>{character.id === activeId ? '使用中' : '切换'}</em>
                </button>
                <div className="character-library-actions">
                  <button
                    className="character-row-action"
                    disabled={busy}
                    onClick={() => { void editCharacter(character) }}
                    title="编辑角色卡"
                    aria-label={`编辑角色 ${character.name}`}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    className="character-row-action is-danger"
                    disabled={busy || characters.length <= 1}
                    onClick={() => { void removeCharacter(character) }}
                    title="删除角色（保留共享模型与声线）"
                    aria-label={`删除角色 ${character.name}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button className="character-import-toggle" onClick={toggleCreateCharacter}>
            <Upload size={16} /> {showCharacterForm
              ? (editingCharacter ? '取消编辑' : '收起创建表单')
              : '创建角色（引用模型与声线）'}
          </button>

          {showCharacterForm && (
            <div className="character-import-form">
              <h3>{editingCharacter ? `编辑角色：${editingCharacter.name}` : '基础信息'}</h3>
              <div className="character-form-grid">
                <label>角色 ID<input value={characterForm.id} disabled={Boolean(editingCharacter)} onChange={event => updateCharacter('id', event.target.value)} placeholder="例如 lantern（小写英文）" /></label>
                <label>显示名称<input value={characterForm.name} onChange={event => updateCharacter('name', event.target.value)} placeholder="角色名称" /></label>
                <label>回复语言<select value={characterForm.replyLanguage} onChange={event => updateCharacter('replyLanguage', event.target.value)}><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="yue">粤语</option></select></label>
                <label>Live2D 模型{editingCharacter && !editingCharacter.resourceReferencesEditable
                  ? <input value={characterForm.modelId} disabled />
                  : <select value={characterForm.modelId} onChange={event => updateCharacter('modelId', event.target.value)}>{models.map(model => <option key={model.id} value={model.id}>{model.id}{model.profile ? '' : '（未注册）'}</option>)}</select>}</label>
                <label>声线{editingCharacter && !editingCharacter.resourceReferencesEditable
                  ? <input value={editingCharacter.voiceName || '角色包内嵌声线'} disabled />
                  : <select value={characterForm.voiceId} onChange={event => updateCharacter('voiceId', event.target.value)}>{voices.map(voice => <option key={voice.id} value={voice.id}>{voice.name}（{voice.promptLang}）</option>)}</select>}</label>
              </div>
              <label>角色设定<textarea value={characterForm.persona} onChange={event => updateCharacter('persona', event.target.value)} placeholder="身份、语气、背景与行为边界" /></label>
              <details className="character-personality-editor">
                <summary>结构化人格（可选，用于稳定长期表现）</summary>
                <p className="character-import-note">每行或逗号分隔一项。这里写角色自身的稳定倾向，不写从对话中学习到的用户信息。</p>
                <div className="character-form-grid">
                  <label>价值观<textarea value={personality.values.join('\n')} onChange={event => updatePersonality({ ...personality, values: listValue(event.target.value) })} placeholder="真诚\n尊重边界" /></label>
                  <label>长期动机<textarea value={personality.motivations.join('\n')} onChange={event => updatePersonality({ ...personality, motivations: listValue(event.target.value) })} placeholder="陪伴用户完成长期目标" /></label>
                  <label>语言气质<textarea value={personality.speechStyle.tone.join('\n')} onChange={event => updatePersonality({ ...personality, speechStyle: { ...personality.speechStyle, tone: listValue(event.target.value) } })} placeholder="自然\n不端着" /></label>
                  <label>语言习惯<textarea value={personality.speechStyle.habits.join('\n')} onChange={event => updatePersonality({ ...personality, speechStyle: { ...personality.speechStyle, habits: listValue(event.target.value) } })} placeholder="句子长短交替" /></label>
                  <label>表达时避免<textarea value={personality.speechStyle.avoid.join('\n')} onChange={event => updatePersonality({ ...personality, speechStyle: { ...personality.speechStyle, avoid: listValue(event.target.value) } })} placeholder="复述系统状态\n说出未发生的动作" /></label>
                  <label>角色自己的喜好<textarea value={personality.selfPreferences.likes.join('\n')} onChange={event => updatePersonality({ ...personality, selfPreferences: { ...personality.selfPreferences, likes: listValue(event.target.value) } })} /></label>
                  <label>角色自己的反感<textarea value={personality.selfPreferences.dislikes.join('\n')} onChange={event => updatePersonality({ ...personality, selfPreferences: { ...personality.selfPreferences, dislikes: listValue(event.target.value) } })} /></label>
                  <label>行为边界<textarea value={personality.boundaries.join('\n')} onChange={event => updatePersonality({ ...personality, boundaries: listValue(event.target.value) })} /></label>
                  <label>初识关系<input value={personality.relationshipStyle.new} onChange={event => updatePersonality({ ...personality, relationshipStyle: { ...personality.relationshipStyle, new: event.target.value } })} /></label>
                  <label>熟悉关系<input value={personality.relationshipStyle.familiar} onChange={event => updatePersonality({ ...personality, relationshipStyle: { ...personality.relationshipStyle, familiar: event.target.value } })} /></label>
                  <label>亲密关系<input value={personality.relationshipStyle.close} onChange={event => updatePersonality({ ...personality, relationshipStyle: { ...personality.relationshipStyle, close: event.target.value } })} /></label>
                </div>
              </details>
              {editingCharacter?.personaOverrideActive && (
                <p className="character-edit-warning">此角色当前存在“角色设定替换”。保存角色卡后，提示词面板中的替换内容仍然优先生效。</p>
              )}
              <p className="character-import-note">{editingCharacter
                ? (editingCharacter.resourceReferencesEditable
                    ? '编辑只会更新角色卡引用，不会修改或删除共享模型与声线。'
                    : '这是完整导入角色包：模型与声线资源保持只读，本次只编辑名称、设定和回复语言。')
                : '创建角色不会复制模型或声线资源；先在“声线/模型”标签页添加系统级资源。'}</p>
              <button className="character-import-submit" disabled={!characterComplete || busy} onClick={() => void submitCharacter()}>
                {busy
                  ? (editingCharacter ? '正在保存…' : '正在创建…')
                  : (editingCharacter ? '保存角色卡' : '创建并启用角色')}
              </button>
            </div>
          )}
        </>
      )}

      {tab === 'voices' && (
        <>
          <div className="character-card-list">
            {!loading && voices.length === 0 && <p className="muted">尚未添加声线。</p>}
            {voices.map(voice => (
              <div key={voice.id} className="character-library-card is-static">
                <span><strong>{voice.name}</strong><small>{voice.id}</small></span>
                <span className="character-library-meta">{voice.promptLang.toUpperCase()} · {voice.configured ? '资源完整' : '资源缺失'}</span>
              </div>
            ))}
          </div>

          <button className="character-import-toggle" onClick={() => setShowVoiceForm(value => !value)}>
            <Upload size={16} /> {showVoiceForm ? '收起添加表单' : '添加系统声线'}
          </button>

          {showVoiceForm && (
            <div className="character-import-form">
              <h3>声线信息</h3>
              <div className="character-form-grid">
                <label>声线 ID<input value={voiceForm.id} onChange={event => updateVoice('id', event.target.value)} placeholder="例如 monika（小写英文）" /></label>
                <label>显示名称<input value={voiceForm.name} onChange={event => updateVoice('name', event.target.value)} placeholder="声线名称" /></label>
                <label>参考音频语言<select value={voiceForm.promptLanguage} onChange={event => updateVoice('promptLanguage', event.target.value)}><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option><option value="yue">粤语</option></select></label>
              </div>
              <label>参考音频原文<textarea value={voiceForm.promptText} onChange={event => updateVoice('promptText', event.target.value)} placeholder="必须与参考音频实际内容一致" /></label>
              <h3>声线资源</h3>
              {VOICE_ASSET_FIELDS.map(([field, kind, label]) => (
                <label className="character-asset-field" key={field}>
                  <span>{label}</span>
                  <div><input value={voiceForm[field]} onChange={event => updateVoice(field, event.target.value)} placeholder="可粘贴绝对路径" /><button type="button" onClick={() => void selectAsset(field, kind)}><FolderOpen size={15} />选择</button></div>
                </label>
              ))}
              <button className="character-import-submit" disabled={!voiceComplete || busy} onClick={() => void submitVoice()}>
                {busy ? '正在添加…' : '添加声线'}
              </button>
            </div>
          )}
        </>
      )}

      {tab === 'models' && (
        <>
          <div className="character-card-list">
            {!loading && models.length === 0 && <p className="muted">尚未发现 Live2D 模型。</p>}
            {models.map(model => (
              <div key={model.id} className={`character-library-card is-static ${model.profile ? '' : 'is-incomplete'}`}>
                <span><strong>{model.id}</strong><small>{model.hasModel3 ? '含 model3.json' : '缺 model3.json'}</small></span>
                <span className="character-library-meta">{model.profile ? '已注册' : '未注册'}</span>
              </div>
            ))}
          </div>
          <p className="character-import-note">将模型目录放入 models/live2d-models/ 后刷新即可发现；"补齐注册"会为缺失项生成 profile。</p>
          <button className="character-import-submit" disabled={busy || models.every(model => model.profile)} onClick={() => void registerAllModels()}>
            {busy ? '正在注册…' : '补齐未注册模型'}
          </button>
        </>
      )}

      {message && <p className="character-manager-message" role="status">{message}</p>}
    </section>
  )
}
