export type ClippingBounds = {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export function createEmptyClippingBounds(): ClippingBounds {
  return {
    minX: Number.MAX_VALUE,
    minY: Number.MAX_VALUE,
    maxX: -Number.MAX_VALUE,
    maxY: -Number.MAX_VALUE,
  }
}

export function includeClippingBounds(
  target: ClippingBounds,
  minX: number,
  minY: number,
  maxX: number,
  maxY: number,
): void {
  if (minX < target.minX) target.minX = minX
  if (minY < target.minY) target.minY = minY
  if (maxX > target.maxX) target.maxX = maxX
  if (maxY > target.maxY) target.maxY = maxY
}
