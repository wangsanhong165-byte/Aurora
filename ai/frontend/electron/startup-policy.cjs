'use strict'

function canEnterCompanion (snapshot) {
  return snapshot?.availability === 'FULL_READY'
}

module.exports = { canEnterCompanion }
