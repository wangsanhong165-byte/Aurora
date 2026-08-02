import { normalizeAvatarViewport, type AvatarViewportConfig } from '../AvatarCapabilityProfile.ts'

export interface ViewportStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export interface PersistedViewport {
  x: number
  y: number
  scale: number
}

export function getViewportStorageKey(modelName: string): string {
  return `live2d_viewport_${modelName}`
}

export function readPersistedViewport(
  storage: ViewportStorage,
  modelName: string,
): PersistedViewport | undefined {
  try {
    const raw = storage.getItem(getViewportStorageKey(modelName))
    if (!raw) return undefined

    const parsed = JSON.parse(raw) as Partial<AvatarViewportConfig>
    if (!isFiniteNumber(parsed.x) || !isFiniteNumber(parsed.y) || !isFiniteNumber(parsed.scale)) {
      return undefined
    }

    return normalizeAvatarViewport(parsed)
  } catch (_) {
    return undefined
  }
}

export function savePersistedViewport(
  storage: ViewportStorage,
  modelName: string,
  viewport: PersistedViewport,
): void {
  try {
    const normalized = normalizeAvatarViewport(viewport)
    storage.setItem(getViewportStorageKey(modelName), JSON.stringify(normalized))
  } catch (_) {
    // localStorage can be unavailable or full; viewport interaction must keep working.
  }
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}
