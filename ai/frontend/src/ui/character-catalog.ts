export type CharacterDescriptor = {
  id: string
  name: string
  replyLanguage: string
  live2dModel: string
  voiceConfigured: boolean
}

export type CharacterForm = {
  id: string
  name: string
  persona: string
  replyLanguage: string
  modelId: string
  voiceId: string
}

export type CharacterDetail = CharacterDescriptor & {
  persona: string
  modelId: string
  voiceId: string
  voiceName: string
  resourceMode: 'reference' | 'embedded'
  resourceReferencesEditable: boolean
  personaOverrideActive: boolean
}

export type VoiceDescriptor = {
  id: string
  name: string
  promptText: string
  promptLang: string
  configured: boolean
}

export type VoiceForm = {
  id: string
  name: string
  promptLanguage: string
  promptText: string
  referenceAudio: string
  t2sModel: string
  vitsModel: string
}

export type ModelDescriptor = {
  id: string
  hasModel3: boolean
  profile: boolean
}

export function buildCharacterPayload(form: CharacterForm) {
  return {
    id: form.id.trim().toLowerCase(),
    name: form.name.trim(),
    persona: form.persona.trim(),
    reply_language: form.replyLanguage,
    model_id: form.modelId,
    voice_id: form.voiceId,
  }
}

export function buildCharacterUpdatePayload(
  form: CharacterForm,
  resourceReferencesEditable: boolean,
) {
  const payload: Record<string, string> = {
    name: form.name.trim(),
    persona: form.persona.trim(),
    reply_language: form.replyLanguage,
  }
  if (resourceReferencesEditable) {
    payload.model_id = form.modelId
    payload.voice_id = form.voiceId
  }
  return payload
}

export function buildVoicePayload(form: VoiceForm) {
  return {
    id: form.id.trim().toLowerCase(),
    name: form.name.trim(),
    prompt_text: form.promptText.trim(),
    prompt_lang: form.promptLanguage,
    reference_audio: form.referenceAudio.trim(),
    t2s_model: form.t2sModel.trim(),
    vits_model: form.vitsModel.trim(),
  }
}

export function readCharacterCatalog(raw: Record<string, unknown>): {
  activeCharacterId: string
  characters: CharacterDescriptor[]
} {
  const items = Array.isArray(raw.characters) ? raw.characters : []
  const characters = items.flatMap(item => {
    if (!item || typeof item !== 'object') return []
    const value = item as Record<string, unknown>
    if (typeof value.id !== 'string' || typeof value.name !== 'string') return []
    return [{
      id: value.id,
      name: value.name,
      replyLanguage: String(value.reply_language || 'en'),
      live2dModel: String(value.live2d_model || ''),
      voiceConfigured: value.voice_configured === true,
    }]
  })
  return {
    activeCharacterId: String(raw.active_character_id || ''),
    characters,
  }
}

export function readCharacterDetail(raw: Record<string, unknown>): CharacterDetail {
  const nested = raw.character
  if (!nested || typeof nested !== 'object') {
    throw new Error('角色详情响应无效')
  }
  const value = nested as Record<string, unknown>
  if (typeof value.id !== 'string' || typeof value.name !== 'string') {
    throw new Error('角色详情缺少 ID 或名称')
  }
  const resourceMode = value.resource_mode === 'reference' ? 'reference' : 'embedded'
  return {
    id: value.id,
    name: value.name,
    persona: String(value.persona || ''),
    replyLanguage: String(value.reply_language || 'en'),
    modelId: String(value.model_id || value.live2d_model || ''),
    voiceId: String(value.voice_id || ''),
    voiceName: String(value.voice_name || value.voice_id || ''),
    resourceMode,
    resourceReferencesEditable: value.resource_references_editable === true,
    personaOverrideActive: value.persona_override_active === true,
    live2dModel: String(value.live2d_model || value.model_id || ''),
    voiceConfigured: value.voice_configured === true,
  }
}

export function readVoiceCatalog(raw: Record<string, unknown>): VoiceDescriptor[] {
  const items = Array.isArray(raw.voices) ? raw.voices : []
  return items.flatMap(item => {
    if (!item || typeof item !== 'object') return []
    const value = item as Record<string, unknown>
    if (typeof value.id !== 'string') return []
    return [{
      id: value.id,
      name: String(value.name || value.id),
      promptText: String(value.prompt_text || ''),
      promptLang: String(value.prompt_lang || 'en'),
      configured: value.configured === true,
    }]
  })
}

export function readModelCatalog(raw: Record<string, unknown>): ModelDescriptor[] {
  const items = Array.isArray(raw.models) ? raw.models : []
  return items.flatMap(item => {
    if (!item || typeof item !== 'object') return []
    const value = item as Record<string, unknown>
    if (typeof value.id !== 'string') return []
    return [{
      id: value.id,
      hasModel3: value.has_model3 === true,
      profile: value.profile === true,
    }]
  })
}
