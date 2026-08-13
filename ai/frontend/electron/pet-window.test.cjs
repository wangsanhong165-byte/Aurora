const assert = require('node:assert/strict')
const test = require('node:test')

const {
  fitBoundsToWorkArea,
  getPetBounds,
  isPointInPetRegions,
  selectRestorableBounds,
} = require('./pet-window.cjs')

test('pet window covers the active display work area', () => {
  assert.deepEqual(
    getPetBounds({ x: 0, y: 0, width: 1920, height: 1080 }),
    { x: 0, y: 0, width: 1920, height: 1080 },
  )
})

test('pet window preserves an offset work area', () => {
  const bounds = getPetBounds({ x: 0, y: 0, width: 800, height: 600 })

  assert.deepEqual(bounds, { x: 0, y: 0, width: 800, height: 600 })
})

test('pet window never loses a tiny offset work area', () => {
  const area = { x: 100, y: 50, width: 300, height: 400 }
  const bounds = getPetBounds(area)

  assert.deepEqual(bounds, area)
})

test('pet hit testing accepts only finite interactive regions', () => {
  const regions = [{ x: 100, y: 200, width: 120, height: 160 }]

  assert.equal(isPointInPetRegions({ x: 100, y: 200 }, regions), true)
  assert.equal(isPointInPetRegions({ x: 220, y: 360 }, regions), true)
  assert.equal(isPointInPetRegions({ x: 221, y: 360 }, regions), false)
  assert.equal(isPointInPetRegions({ x: 120, y: 240 }, [{ x: 'bad' }]), false)
})

test('normal bounds are fitted back onto the current display', () => {
  assert.deepEqual(
    fitBoundsToWorkArea(
      { x: 2400, y: -300, width: 1200, height: 800 },
      { x: 0, y: 0, width: 1920, height: 1040 },
    ),
    { x: 720, y: 0, width: 1200, height: 800 },
  )
})

test('maximized windows preserve their pre-maximize normal bounds', () => {
  assert.deepEqual(
    selectRestorableBounds({
      current: { x: 0, y: 0, width: 1920, height: 1080 },
      normal: { x: 220, y: 140, width: 1200, height: 800 },
      maximized: true,
      fullScreen: false,
    }),
    { x: 220, y: 140, width: 1200, height: 800 },
  )
})
