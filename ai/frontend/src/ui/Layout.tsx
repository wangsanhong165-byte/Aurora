import { useEffect, useReducer, useRef, type PointerEvent, type ReactNode } from 'react'

import {
  DEFAULT_DRAWER_WIDTH,
  createInitialDrawerState,
  reduceDrawerState,
  type DrawerSection,
} from './workspace-state'

export interface DrawerItem {
  id: DrawerSection
  label: string
  mark: string
}

export interface LayoutProps {
  characterArea: ReactNode
  subtitle: ReactNode
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
  drawerItems,
  renderDrawer,
  petMode = false,
  onExitPetMode,
}: LayoutProps) {
  const [drawer, dispatch] = useReducer(reduceDrawerState, undefined, initialDrawerState)
  const stopResizeRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (drawer.active) localStorage.setItem(ACTIVE_KEY, drawer.active)
    else localStorage.setItem(ACTIVE_KEY, 'closed')
    localStorage.setItem(WIDTH_KEY, String(drawer.width))
  }, [drawer])

  useEffect(() => () => stopResizeRef.current?.(), [])

  const beginResize = (event: PointerEvent<HTMLDivElement>) => {
    stopResizeRef.current?.()
    event.currentTarget.setPointerCapture(event.pointerId)
    const startX = event.clientX
    const startWidth = drawer.width
    const onMove = (moveEvent: globalThis.PointerEvent) => {
      dispatch({ type: 'resize', width: startWidth + startX - moveEvent.clientX })
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

  return (
    <div className={`workspace-shell ${petMode ? 'is-pet-mode' : ''}`}>
      <main
        className="companion-stage"
        onDoubleClick={petMode ? onExitPetMode : undefined}
        title={petMode ? '双击返回舞台模式' : undefined}
      >
        <div className="character-stage">{characterArea}</div>
        {subtitle}
        {petMode && (
          <div className="pet-window-controls">
            <span className="pet-drag-handle" title="拖动桌宠窗口">拖动</span>
            <button type="button" onClick={onExitPetMode}>返回舞台</button>
          </div>
        )}
      </main>

      {!petMode && drawer.active && (
        <aside
          className="stage-drawer"
          style={{ width: drawer.width, flexBasis: drawer.width }}
          aria-label={`${drawerItems.find(item => item.id === drawer.active)?.label ?? ''}面板`}
        >
          <div
            className="drawer-resize-handle"
            onPointerDown={beginResize}
            role="separator"
            aria-orientation="vertical"
            aria-label="调整面板宽度"
          />
          {renderDrawer(drawer.active)}
        </aside>
      )}

      {!petMode && (
        <aside className="stage-rail" aria-label="功能导航">
          <nav>
            {drawerItems.map(item => (
              <button
                key={item.id}
                type="button"
                className={drawer.active === item.id ? 'is-active' : ''}
                onClick={() => dispatch({ type: 'select', section: item.id })}
                title={item.label}
                aria-label={item.label}
                aria-pressed={drawer.active === item.id}
              >
                <span aria-hidden="true">{item.mark}</span>
              </button>
            ))}
          </nav>
        </aside>
      )}
    </div>
  )
}
