export interface DrawableBounds {
  left: number
  right: number
  top: number
  bottom: number
  centerX: number
  centerY: number
}

/** Find the visual center of a model from its drawable vertex positions. */
export function computeDrawableBounds(
  drawables: ReadonlyArray<ArrayLike<number> | null | undefined>,
): DrawableBounds | null {
  let left = Infinity
  let right = -Infinity
  let top = Infinity
  let bottom = -Infinity

  for (const vertices of drawables) {
    if (!vertices || typeof vertices.length !== 'number') continue
    for (let index = 0; index + 1 < vertices.length; index += 2) {
      const x = Number(vertices[index])
      const y = Number(vertices[index + 1])
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      left = Math.min(left, x)
      right = Math.max(right, x)
      top = Math.min(top, y)
      bottom = Math.max(bottom, y)
    }
  }

  if (![left, right, top, bottom].every(Number.isFinite)) return null
  return { left, right, top, bottom, centerX: (left + right) / 2, centerY: (top + bottom) / 2 }
}
