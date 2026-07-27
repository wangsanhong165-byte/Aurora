import { useEffect, useState } from 'react'

import { STAGE_SUBTITLE_DURATION_MS, toStageSubtitle } from './stage-subtitle'

export function StageSubtitle({ text }: { text: string }) {
  const [visibleText, setVisibleText] = useState('')

  useEffect(() => {
    const subtitle = toStageSubtitle(text)
    if (!subtitle) return
    setVisibleText(subtitle)
    const timer = window.setTimeout(() => setVisibleText(''), STAGE_SUBTITLE_DURATION_MS)
    return () => window.clearTimeout(timer)
  }, [text])

  return (
    <div className={`stage-subtitle ${visibleText ? 'is-visible' : ''}`} aria-live="polite">
      {visibleText && <p>{visibleText}</p>}
    </div>
  )
}
