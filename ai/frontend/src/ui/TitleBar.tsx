import { memo } from 'react'
import { Minus, Maximize2, X } from 'lucide-react'
import { electronWindowBridge } from '../session/electron-window-bridge'

export const TitleBar = memo(function TitleBar() {
  const api = electronWindowBridge

  return (
    <header className="title-bar" aria-label="窗口控制区">
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
