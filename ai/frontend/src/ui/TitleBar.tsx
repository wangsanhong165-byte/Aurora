import { memo, useRef, type PointerEvent, type MouseEvent } from 'react'
import { Minus, Maximize2, X } from 'lucide-react'
import { electronWindowBridge } from '../session/electron-window-bridge'
import { setWindowDragging } from '../character/window-drag-state'

// Window dragging is driven explicitly over IPC (not CSS -webkit-app-region,
// which proved unreliable for moving this window): pointerdown starts the drag,
// pointerup ends it, and the main process polls the OS cursor to move the
// window. Buttons inside .window-controls must keep normal click behavior.
export const TitleBar = memo(function TitleBar() {
  const api = electronWindowBridge
  const draggingRef = useRef(false)

  const beginDrag = (event: PointerEvent<HTMLHeadElement>) => {
    if (event.button !== 0) return
    if ((event.target as HTMLElement).closest('.window-controls')) return
    event.currentTarget.setPointerCapture(event.pointerId)
    draggingRef.current = true
    setWindowDragging(true)
    api.startWindowDrag()
  }

  const endDrag = () => {
    if (!draggingRef.current) return
    draggingRef.current = false
    setWindowDragging(false)
    api.endWindowDrag()
  }

  const toggleMaximize = (event: MouseEvent<HTMLHeadElement>) => {
    if ((event.target as HTMLElement).closest('.window-controls')) return
    void api.maximize()
  }

  return (
    <header
      className="title-bar"
      aria-label="窗口控制区"
      onPointerDown={beginDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={toggleMaximize}
    >
      <span className="title-bar-drag-region" aria-hidden="true" />
      <div className="window-controls">
        {api && (
          <>
            <button type="button" onClick={() => api.minimize()} aria-label="最小化" title="最小化">
              <Minus aria-hidden="true" />
            </button>
            <button type="button" onClick={() => api.maximize()} aria-label="最大化" title="最大化">
              <Maximize2 aria-hidden="true" />
            </button>
            <button type="button" className="window-close" onClick={() => api.close()} aria-label="关闭" title="关闭">
              <X aria-hidden="true" />
            </button>
          </>
        )}
      </div>
    </header>
  )
})
