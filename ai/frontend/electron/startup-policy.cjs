'use strict'

/**
 * Decide whether the companion main window can load.
 *
 * TEXT_READY (llm + bridge) is sufficient — the user can interact
 * while ASR/TTS continue loading in the background.
 * FULL_READY is no longer required, preventing voice service delays
 * from blocking the entire UI.
 */
function canEnterCompanion (snapshot) {
  if (!snapshot) return false
  // FULL_READY and TEXT_READY both unlock the UI.
  // VOICE_READY without TEXT_READY should not occur in practice,
  // but BLOCKED means the platform hasn't started yet.
  return snapshot.availability === 'FULL_READY'
    || snapshot.availability === 'VOICE_READY'
    || snapshot.availability === 'TEXT_READY'
}

module.exports = { canEnterCompanion }
