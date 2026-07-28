import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clampDrawerWidth,
  createInitialDrawerState,
  reduceDrawerState,
  type DrawerState,
} from './workspace-state.ts'
import { isStageSubtitleVisible, toStageSubtitle } from './stage-subtitle.ts'
import { resolveHistoryCommand } from '../conversation/history-command.ts'
import { observeElementResize } from '../character/observe-resize.ts'

test('navigation selects content without closing the drawer', () => {
  const initial: DrawerState = { section: 'history', expanded: true, width: 380 }

  assert.deepEqual(reduceDrawerState(initial, { type: 'select', section: 'history' }), {
    section: 'history',
    expanded: true,
    width: 380,
  })
  assert.deepEqual(reduceDrawerState(initial, { type: 'select', section: 'settings' }), {
    section: 'settings',
    expanded: true,
    width: 380,
  })
})

test('drawer expansion changes only through the dedicated toggle action', () => {
  const initial: DrawerState = { section: 'history', expanded: true, width: 380 }

  assert.deepEqual(reduceDrawerState(initial, { type: 'toggle' }), {
    section: 'history',
    expanded: false,
    width: 380,
  })
  assert.deepEqual(
    reduceDrawerState({ ...initial, expanded: false }, { type: 'select', section: 'memory' }),
    { section: 'memory', expanded: true, width: 380 },
  )
})

test('drawer width stays inside the supported stage-safe range', () => {
  assert.equal(clampDrawerWidth(240), 300)
  assert.equal(clampDrawerWidth(420), 420)
  assert.equal(clampDrawerWidth(700), 520)
})

test('invalid persisted drawer preferences fall back to safe defaults', () => {
  assert.deepEqual(createInitialDrawerState('unknown', 900), {
    section: 'history',
    expanded: true,
    width: 520,
  })
})

test('persisted closed drawer restores as closed', () => {
  assert.deepEqual(createInitialDrawerState('closed', 380), {
    section: 'history',
    expanded: false,
    width: 380,
  })
})

test('stage subtitle remains visible for 4.5 seconds after the last update', () => {
  assert.equal(isStageSubtitleVisible(10_000, 14_499), true)
  assert.equal(isStageSubtitleVisible(10_000, 14_500), false)
})

test('stage subtitle shows only the latest sentence instead of the full reply', () => {
  assert.equal(
    toStageSubtitle('第一句已经说完。现在只显示这一句。'),
    '现在只显示这一句。',
  )
})

test('history loading only completes after a matching command response', () => {
  assert.deepEqual(resolveHistoryCommand('load_history', {
    history_uid: 'hist_1',
    messages: [{ role: 'assistant', content: '你好' }],
  }), {
    activeUid: 'hist_1',
    clearMessages: false,
    messages: [{ role: 'assistant', content: '你好' }],
    refreshHistories: false,
  })

  assert.deepEqual(resolveHistoryCommand('create_history', {
    history_uid: 'hist_2',
  }), {
    activeUid: 'hist_2',
    clearMessages: true,
    messages: null,
    refreshHistories: true,
  })
})

test('element resize observer reports layout changes and disconnects on cleanup', () => {
  let observed: object | null = null
  let disconnected = false
  let resized = 0
  class FakeResizeObserver {
    private readonly callback: () => void
    constructor(callback: () => void) {
      this.callback = callback
    }
    observe(element: object) {
      observed = element
      this.callback()
    }
    disconnect() {
      disconnected = true
    }
  }
  const element = {}
  const cleanup = observeElementResize(
    element,
    () => { resized += 1 },
    FakeResizeObserver,
  )

  assert.equal(observed, element)
  assert.equal(resized, 1)
  cleanup()
  assert.equal(disconnected, true)
})
