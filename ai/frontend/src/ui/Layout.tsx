import { ChevronRight } from 'lucide-react'
import { useEffect, useReducer, useRef, useState, type MouseEvent, type PointerEvent, type ReactNode } from 'react'

import {
  DEFAULT_DRAWER_WIDTH,
  createInitialDrawerState,
  reduceDrawerState,
  type DrawerSection,
} from './workspace-state'
import { createFrameCoalescer, type FrameCoalescer } from './frame-coalescer'
import {
  clampPetPosition,
  DEFAULT_PET_SIZE,
  readPetPosition,
  writePetPosition,
  type PetPosition,
} from './pet-position'
import { electronWindowBridge } from '../session/electron-window-bridge'

export interface DrawerItem {
  id: DrawerSection
  label: string
  icon: ReactNode
  placement?: 'main' | 'bottom'
}

export interface LayoutProps {
  characterArea: ReactNode
  background?: ReactNode
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
  background,
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
  const characterRef = useRef<HTMLDivElement>(null)
  const conversationRef = useRef<HTMLDivElement>(null)
  const controlsRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ active: boolean; didMove: boolean; startX: number; startY: number; offsetX: number; offsetY: number }>({
    active: false,
    didMove: false,
    startX: 0,
    startY: 0,
    offsetX: 0,
    offsetY: 0,
  })
  const petPositionRef = useRef<PetPosition>({ x: 0, y: 0 })
  const passthroughTimerRef = useRef<number | null>(null)
  const [petPosition, setPetPosition] = useState<PetPosition>(() => (
    petMode
      ? readPetPosition(window.localStorage, { width: window.innerWidth, height: window.innerHeight })
      : { x: 0, y: 0 }
  ))
  petPositionRef.current = petPosition

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

  useEffect(() => {
    if (!petMode) {
      dragRef.current.active = false
      electronWindowBridge.setPetMousePassthrough(false)
      return
    }

    setPetPosition(readPetPosition(
      window.localStorage,
      { width: window.innerWidth, height: window.innerHeight },
    ))

    const updatePetPosition = () => {
      setPetPosition(current => clampPetPosition(
        current,
        { width: window.innerWidth, height: window.innerHeight },
      ))
    }
    const setPassthroughFromPoint = (clientX: number, clientY: number) => {
      if (dragRef.current.active) return
      const regions = [characterRef.current, conversationRef.current, controlsRef.current]
        .filter((element): element is HTMLDivElement => Boolean(element))
      const interactive = regions.some(element => {
        const rect = element.getBoundingClientRect()
        return clientX >= rect.left && clientX <= rect.right
          && clientY >= rect.top && clientY <= rect.bottom
      })
      electronWindowBridge.setPetMousePassthrough(!interactive)
    }
    const onMouseMove = (event: globalThis.MouseEvent) => {
      if (dragRef.current.active) {
        if (!dragRef.current.didMove) {
          dragRef.current.didMove = Math.hypot(
            event.clientX - dragRef.current.startX,
            event.clientY - dragRef.current.startY,
          ) >= 4
        }
        if (!dragRef.current.didMove) return
        const next = clampPetPosition(
          {
            x: event.clientX - dragRef.current.offsetX,
            y: event.clientY - dragRef.current.offsetY,
          },
          { width: window.innerWidth, height: window.innerHeight },
        )
        setPetPosition(next)
        return
      }
      setPassthroughFromPoint(event.clientX, event.clientY)
    }
    const onMouseUp = () => {
      if (!dragRef.current.active) return
      dragRef.current.active = false
      writePetPosition(window.localStorage, petPositionRef.current)
      if (dragRef.current.didMove) {
        electronWindowBridge.setPetMousePassthrough(true)
      } else {
        passthroughTimerRef.current = window.setTimeout(() => {
          passthroughTimerRef.current = null
          electronWindowBridge.setPetMousePassthrough(true)
        }, 120)
      }
    }
    updatePetPosition()
    window.addEventListener('resize', updatePetPosition)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    electronWindowBridge.setPetMousePassthrough(true)
    return () => {
      window.removeEventListener('resize', updatePetPosition)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
      if (passthroughTimerRef.current !== null) {
        window.clearTimeout(passthroughTimerRef.current)
        passthroughTimerRef.current = null
      }
      electronWindowBridge.setPetMousePassthrough(false)
    }
  }, [petMode])

  const beginPetDrag = (event: MouseEvent<HTMLDivElement>) => {
    if (!petMode || event.button !== 0) return
    const rect = characterRef.current?.getBoundingClientRect()
    if (!rect) return
    event.preventDefault()
    event.stopPropagation()
    if (passthroughTimerRef.current !== null) {
      window.clearTimeout(passthroughTimerRef.current)
      passthroughTimerRef.current = null
    }
    dragRef.current = {
      active: true,
      didMove: false,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    }
    electronWindowBridge.setPetMousePassthrough(false)
  }

  const suppressPetDragClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!petMode || !dragRef.current.didMove) return
    event.preventDefault()
    event.stopPropagation()
    dragRef.current.didMove = false
    electronWindowBridge.setPetMousePassthrough(true)
  }

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
      {!petMode && (
        <aside className="stage-rail" aria-label="功能导航">
          <nav aria-label="主要功能">
            {drawerItems.filter(item => item.placement !== 'bottom').map(renderNavButton)}
          </nav>
          <nav className="rail-bottom" aria-label="开发功能">
            {drawerItems.filter(item => item.placement === 'bottom').map(renderNavButton)}
          </nav>
        </aside>
      )}

      <main
        className="companion-stage"
      >
        {background}
        <div
          ref={characterRef}
          className="character-stage"
          style={petMode ? {
            left: petPosition.x,
            top: petPosition.y,
            width: DEFAULT_PET_SIZE.width,
            height: DEFAULT_PET_SIZE.height,
          } : undefined}
          onMouseDownCapture={petMode ? beginPetDrag : undefined}
          onClickCapture={petMode ? suppressPetDragClick : undefined}
        >
          {characterArea}
        </div>
        {subtitle}
        {!petMode && <div className="stage-conversation">{conversationArea}</div>}
        {petMode && (
          <div
            ref={conversationRef}
            className="pet-conversation-layer"
            style={{
              left: petPosition.x,
              top: petPosition.y > 252
                ? Math.max(12, petPosition.y - 228)
                : Math.min(window.innerHeight - 236, petPosition.y + DEFAULT_PET_SIZE.height + 12),
              width: DEFAULT_PET_SIZE.width,
            }}
          >
            {conversationArea}
          </div>
        )}
        {petMode && (
          <div
            ref={controlsRef}
            className="pet-window-controls"
            style={{ left: petPosition.x + 10, top: petPosition.y + 10 }}
          >
            <span className="pet-drag-handle" title="拖动桌宠">拖动桌宠</span>
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
          <button
            type="button"
            className="drawer-edge-toggle is-expanded"
            onClick={() => dispatch({ type: 'toggle' })}
            aria-label="收起侧栏"
            title="收起侧栏"
          >
            <ChevronRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </button>
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
    </div>
  )
}
