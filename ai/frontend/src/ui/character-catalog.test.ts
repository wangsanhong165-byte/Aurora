import assert from 'node:assert/strict'
import test from 'node:test'

import { buildCharacterImportPayload, readCharacterCatalog } from './character-catalog.ts'

test('builds one complete import payload without mixing reply and reference languages', () => {
  assert.deepEqual(buildCharacterImportPayload({
    id: ' Lantern ', name: 'Lantern', persona: 'A concise persona.',
    replyLanguage: 'zh', promptLanguage: 'ja', promptText: 'reference transcript',
    live2dDirectory: 'C:/assets/live2d', referenceAudio: 'C:/assets/reference.wav',
    t2sModel: 'C:/assets/voice.ckpt', vitsModel: 'C:/assets/voice.pth',
  }), {
    id: 'lantern', name: 'Lantern', persona: 'A concise persona.', reply_language: 'zh',
    voice: { prompt_language: 'ja', prompt_text: 'reference transcript' },
    assets: {
      live2d_directory: 'C:/assets/live2d', reference_audio: 'C:/assets/reference.wav',
      t2s_model: 'C:/assets/voice.ckpt', vits_model: 'C:/assets/voice.pth',
    },
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
