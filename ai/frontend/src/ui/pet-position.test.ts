import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  clampPetPosition,
  defaultPetPosition,
  readPetPosition,
  writePetPosition,
} from './pet-position.ts'

describe('desktop pet position', () => {
  it('clamps a dragged pet inside the current viewport', () => {
    assert.deepEqual(clampPetPosition({ x: -20, y: 900 }, { width: 1280, height: 720 }), { x: 0, y: 100 })
  })

  it('defaults to the lower-right area without escaping', () => {
    assert.deepEqual(defaultPetPosition({ width: 1920, height: 1080 }), { x: 1452, y: 436 })
  })

  it('round-trips persisted position and clamps stale display coordinates', () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    }
    writePetPosition(storage, { x: 1600, y: 900 })
    assert.deepEqual(readPetPosition(storage, { width: 1280, height: 720 }), { x: 860, y: 100 })
  })
})
