const assert = require('node:assert/strict')
const test = require('node:test')

const {
  fitBoundsToWorkArea,
  getPetBounds,
  selectRestorableBounds,
} = require('./pet-window.cjs')

test('pet window is placed inside the lower-right work area', () => {
  assert.deepEqual(
    getPetBounds({ x: 0, y: 0, width: 1920, height: 1080 }),
    { x: 1456, y: 376, width: 440, height: 680 },
  )
})

test('pet window stays usable on a compact display', () => {
  const bounds = getPetBounds({ x: 0, y: 0, width: 800, height: 600 })

  assert.ok(bounds.width >= 320)
  assert.ok(bounds.height >= 480)
  assert.ok(bounds.x >= 0)
  assert.ok(bounds.y >= 0)
  assert.ok(bounds.x + bounds.width <= 800)
  assert.ok(bounds.y + bounds.height <= 600)
})

test('pet window never escapes a tiny offset work area', () => {
  const area = { x: 100, y: 50, width: 300, height: 400 }
  const bounds = getPetBounds(area)

  assert.ok(bounds.x >= area.x)
  assert.ok(bounds.y >= area.y)
  assert.ok(bounds.x + bounds.width <= area.x + area.width)
  assert.ok(bounds.y + bounds.height <= area.y + area.height)
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
