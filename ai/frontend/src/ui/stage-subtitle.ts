export const STAGE_SUBTITLE_DURATION_MS = 4500
export const STAGE_SUBTITLE_MAX_LENGTH = 96

export function isStageSubtitleVisible(
  shownAt: number,
  now: number,
  durationMs = STAGE_SUBTITLE_DURATION_MS,
): boolean {
  return now - shownAt < durationMs
}

export function toStageSubtitle(
  text: string,
  maxLength = STAGE_SUBTITLE_MAX_LENGTH,
): string {
  const segments = text.trim().match(/[^。！？!?\n]+[。！？!?]?/g) ?? []
  const latest = segments.at(-1)?.trim() ?? ''
  if (latest.length <= maxLength) return latest
  return `…${latest.slice(-(maxLength - 1))}`
}
