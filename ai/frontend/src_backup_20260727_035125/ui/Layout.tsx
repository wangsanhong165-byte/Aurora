import { useEffect, useReducer, useRef, type PointerEvent, type ReactNode } from 'react'

import {
  DEFAULT_DRAWER_WIDTH,
  createInitialDrawerState,
  reduceDrawerState,
  type DrawerSection,
} from './workspace-state'
import { createFrameCoalescer, type FrameCoalescer } from './frame-coalescer'

export interface DrawerItem {
  id: DrawerSection
  label: string
  icon: ReactNode
  placement?: 'main' | 'bottom'
}

export interface LayoutProps {
  characterArea: ReactNode
  subtitle: ReactNode
  conversationArea: ReactNode
  drawerItems: DrawerItem[]
  renderDrawer: (section: DrawerSection) => ReactNode
  petMode?: boolean
  onExitPetMode?: () => void
}

const ACTIVE_KEY = 'ui.stage.drawer.active'
const WIDTH_KEY = 'ui.stage.drawer.width'

function initialDrawerState() {
  const storedActive = localStorage.getItem(ACTIVE_KEY)
  const storedWidth = Number(localStorage.getItem(WIDTH_KEY))
  return createInitialDrawerState(storedActive, storedWidth || DEFAULT_DRAWER_WIDTH)
}

export function Layout({
  characterArea,
  subtitle,
  conversationArea,
  drawerItems,
  renderDrawer,
  petMode = false,
  onExitPetMode,
}: LayoutProps) {
  const [drawer, dispatch] = useReducer(reduceDrawerState, undefined, initialDrawerState)
  const stopResizeRef = useRef<(() => void) | null>(null)
  const resizeCoalescerRef = useRef<FrameCoalescer<number> | null>(null)
  if (!resizeCoalescerRef.current) {
    resizeCoalescerRef.current = createFrameCoalescer(
      width => dispatch({ type: 'resize', width }),
    )
  }

  useEffect(() => {
    localStorage.setItem(ACTIVE_KEY, drawer.expanded ? drawer.section : 'closed')
    localStorage.setItem(WIDTH_KEY, String(drawer.width))
  }, [drawer])

  useEffect(() => () => {
    stopResizeRef.current?.()
    resizeCoalescerRef.current?.cancel()
  }, [])

  const beginResize = (event: PointerEvent<HTMLDivElement>) => {
    stopResizeRef.current?.()
    event.currentTarget.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const startWidth = drawer.width
    const onMove = (moveEvent: globalThis.PointerEvent) => {
      resizeCoalescerRef.current?.schedule(startWidth + startX - moveEvent.clientX)
    }
    const onEnd = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onEnd)
      window.removeEventListener('pointercancel', onEnd)
      stopResizeRef.current = null
    }
    stopResizeRef.current = onEnd
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onEnd)
    window.addEventListener('pointercancel', onEnd)
  }

  const renderNavButton = (item: DrawerItem) => (
    <button
      key={item.id}
      type="button"
      className={drawer.section === item.id ? 'is-active' : ''}
      onClick={() => dispatch({ type: 'select', section: item.id })}
      title={item.label}
      aria-label={item.label}
      aria-pressed={drawer.section === item.id}
    >
      <span aria-hidden="true">{item.icon}</span>
    </button>
  )

  return (
    <div className={`workspace-shell ${petMode ? 'is-pet-mode' : ''}`}>
      <main
        className="companion-stage"
        onDoubleClick={petMode ? onExitPetMode : undefined}
        title={petMode ? '双击返回舞台模式' : undefined}
      >
        <div className="character-stage">{characterArea}</div>
        {subtitle}
        {!petMode && <div className="stage-conversation">{conversationArea}</div>}
        {petMode && (
          <div className="pet-window-controls">
            <span className="pet-drag-handle" title="拖动桌宠窗口">拖动</span>
            <button type="button" onClick={onExitPetMode}>返回舞台</button>
          </div>
        )}
      </main>

      {!petMode && drawer.expanded && (
        <aside
          className="stage-drawer"
          style={{ width: drawer.width, flexBasis: drawer.width }}
          aria-label={`${drawerItems.find(item => item.id === drawer.section)?.label ?? ''}面板`}
        >
          <div
            className="drawer-resize-handle"
            onPointerDown={beginResize}
            role="separator"
            aria-orientation="vertical"
            aria-label="调整面板宽度"
          />
          {renderDrawer(drawer.section)}
        </aside>
      )}

      {!petMode && (
        <aside className="stage-rail" aria-label="功能导航">
          <button
            type="button"
            className={`drawer-edge-toggle ${drawer.expanded ? 'is-expanded' : ''}`}
            onClick={() => dispatch({ type: 'toggle' })}
            aria-label={drawer.expanded ? '收起侧栏' : '展开侧栏'}
            aria-expanded={drawer.expanded}
            title={drawer.expanded ? '收起侧栏' : '展开侧栏'}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <nav aria-label="主要功能">
            {drawerItems.filter(item => item.placement !== 'bottom').map(renderNavButton)}
          </nav>
          <nav className="rail-bottom" aria-label="开发功能">
            {drawerItems.filter(item => item.placement === 'bottom').map(renderNavButton)}
          </nav>
        </aside>
      )}
    </div>
  )
}
