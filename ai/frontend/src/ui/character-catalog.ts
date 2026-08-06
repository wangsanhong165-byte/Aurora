export type CharacterDescriptor = {
  id: string
  name: string
  replyLanguage: string
  live2dModel: string
  voiceConfigured: boolean
}

export type CharacterImportForm = {
  id: string
  name: string
  persona: string
  replyLanguage: string
  promptLanguage: string
  promptText: string
  live2dDirectory: string
  referenceAudio: string
  t2sModel: string
  vitsModel: string
}

export function buildCharacterImportPayload(form: CharacterImportForm) {
  return {
    id: form.id.trim().toLowerCase(),
    name: form.name.trim(),
    persona: form.persona.trim(),
    reply_language: form.replyLanguage,
    voice: {
      prompt_language: form.promptLanguage,
      prompt_text: form.promptText.trim(),
    },
    assets: {
      live2d_directory: form.live2dDirectory.trim(),
      reference_audio: form.referenceAudio.trim(),
      t2s_model: form.t2sModel.trim(),
      vits_model: form.vitsModel.trim(),
    },
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
