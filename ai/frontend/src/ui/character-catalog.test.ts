import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCharacterPayload,
  buildCharacterUpdatePayload,
  buildVoicePayload,
  readCharacterCatalog,
  readCharacterDetail,
  readModelCatalog,
  readVoiceCatalog,
} from './character-catalog.ts'

test('builds a thin reference character payload with model and voice ids', () => {
  assert.deepEqual(buildCharacterPayload({
    id: ' Lantern ', name: 'Lantern', persona: 'A concise persona.',
    replyLanguage: 'zh', modelId: 'Design_genius_White', voiceId: 'monika',
  }), {
    id: 'lantern', name: 'Lantern', persona: 'A concise persona.', reply_language: 'zh',
    model_id: 'Design_genius_White', voice_id: 'monika',
  })
})

test('builds a voice pack payload without mixing reply and reference languages', () => {
  assert.deepEqual(buildVoicePayload({
    id: ' Monika ', name: 'Monika', promptLanguage: 'en', promptText: 'reference',
    referenceAudio: 'C:/assets/reference.wav', t2sModel: 'C:/assets/voice.ckpt',
    vitsModel: 'C:/assets/voice.pth',
  }), {
    id: 'monika', name: 'Monika', prompt_text: 'reference', prompt_lang: 'en',
    reference_audio: 'C:/assets/reference.wav', t2s_model: 'C:/assets/voice.ckpt',
    vits_model: 'C:/assets/voice.pth',
  })
})

test('reads only valid dynamic character descriptors from management data', () => {
  assert.deepEqual(readCharacterCatalog({
    active_character_id: 'lantern',
    characters: [
      { id: 'lantern', name: 'Lantern', reply_language: 'zh', live2d_model: 'lantern', voice_configured: true },
      { name: 'broken' },
    ],
  }), {
    activeCharacterId: 'lantern',
    characters: [
      { id: 'lantern', name: 'Lantern', replyLanguage: 'zh', live2dModel: 'lantern', voiceConfigured: true },
    ],
  })
})

test('reads voice descriptors and drops malformed entries', () => {
  assert.deepEqual(readVoiceCatalog({
    voices: [
      { id: 'monika', name: 'Monika', prompt_text: 'reference', prompt_lang: 'en', configured: true },
      { name: 'broken' },
    ],
  }), [
    { id: 'monika', name: 'Monika', promptText: 'reference', promptLang: 'en', configured: true },
  ])
})

test('reads model descriptors with registration state', () => {
  assert.deepEqual(readModelCatalog({
    models: [
      { id: 'Design_genius_White', has_model3: true, profile: true },
      { id: 'new_model', has_model3: true, profile: false },
    ],
  }), [
    { id: 'Design_genius_White', hasModel3: true, profile: true },
    { id: 'new_model', hasModel3: true, profile: false },
  ])
})

test('reads editable character detail without exposing the raw character card', () => {
  assert.deepEqual(readCharacterDetail({
    character: {
      id: 'lantern', name: 'Lantern', persona: 'A concise persona.',
      reply_language: 'zh', model_id: 'Design_genius_White', voice_id: 'monika',
      voice_name: 'Monika', resource_mode: 'reference',
      resource_references_editable: true, persona_override_active: true,
      live2d_model: 'Design_genius_White', voice_configured: true,
    },
  }), {
    id: 'lantern', name: 'Lantern', persona: 'A concise persona.',
    replyLanguage: 'zh', modelId: 'Design_genius_White', voiceId: 'monika',
    voiceName: 'Monika', resourceMode: 'reference',
    resourceReferencesEditable: true, personaOverrideActive: true,
    live2dModel: 'Design_genius_White', voiceConfigured: true,
  })
})

test('builds a reference-character update without a mutable character id', () => {
  assert.deepEqual(buildCharacterUpdatePayload({
    id: 'lantern', name: 'Lantern Prime', persona: 'Updated persona.',
    replyLanguage: 'ja', modelId: 'new-model', voiceId: 'new-voice',
  }, true), {
    name: 'Lantern Prime', persona: 'Updated persona.', reply_language: 'ja',
    model_id: 'new-model', voice_id: 'new-voice',
  })
})

test('omits locked embedded resources from a character update', () => {
  assert.deepEqual(buildCharacterUpdatePayload({
    id: 'lantern', name: 'Lantern Prime', persona: 'Updated persona.',
    replyLanguage: 'ja', modelId: 'embedded-model', voiceId: '',
  }, false), {
    name: 'Lantern Prime', persona: 'Updated persona.', reply_language: 'ja',
  })
})
