import assert from 'node:assert/strict'
import { test } from 'node:test'

import { theme } from './theme.ts'

test('workspace theme uses a lifted blue-gray surface hierarchy', () => {
  assert.equal(theme.colors.bg.root, '#1a2030')
  assert.equal(theme.colors.bg.panel, '#232b3d')
  assert.equal(theme.colors.bg.surface, '#2d374b')
  assert.equal(theme.colors.bg.hover, '#37435a')
  assert.equal(theme.colors.text.primary, '#eef0f7')
  assert.equal(theme.colors.text.secondary, '#aab2c2')
  assert.equal(theme.colors.accent, '#d97757')
})

test('workspace theme exposes a consistent icon scale', () => {
  assert.deepEqual(theme.icon, {
    nav: 18,
    action: 16,
    compact: 14,
    strokeWidth: 1.75,
  })
})
