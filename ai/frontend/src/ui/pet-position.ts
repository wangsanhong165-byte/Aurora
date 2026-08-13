export interface PetPosition {
  x: number
  y: number
}

export interface PetViewport {
  width: number
  height: number
}

export interface PetSize {
  width: number
  height: number
}

export const PET_POSITION_STORAGE_KEY = 'ui.pet.position'
export const DEFAULT_PET_SIZE: PetSize = { width: 420, height: 620 }

export function clampPetPosition(
  position: PetPosition,
  viewport: PetViewport,
  size: PetSize = DEFAULT_PET_SIZE,
): PetPosition {
  const maxX = Math.max(0, viewport.width - size.width)
  const maxY = Math.max(0, viewport.height - size.height)
  return {
    x: Math.min(maxX, Math.max(0, Number.isFinite(position.x) ? position.x : 0)),
    y: Math.min(maxY, Math.max(0, Number.isFinite(position.y) ? position.y : 0)),
  }
}

export function defaultPetPosition(viewport: PetViewport, size: PetSize = DEFAULT_PET_SIZE): PetPosition {
  return clampPetPosition(
    { x: viewport.width - size.width - 48, y: viewport.height - size.height - 24 },
    viewport,
    size,
  )
}

export function readPetPosition(
  storage: Pick<Storage, 'getItem'>,
  viewport: PetViewport,
  size: PetSize = DEFAULT_PET_SIZE,
): PetPosition {
  try {
    const raw = storage.getItem(PET_POSITION_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<PetPosition>
      if (Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) {
        return clampPetPosition({ x: parsed.x!, y: parsed.y! }, viewport, size)
      }
    }
  } catch (_) {}
  return defaultPetPosition(viewport, size)
}

export function writePetPosition(storage: Pick<Storage, 'setItem'>, position: PetPosition): void {
  try {
    storage.setItem(PET_POSITION_STORAGE_KEY, JSON.stringify(position))
  } catch (_) {}
}
