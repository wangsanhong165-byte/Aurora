const defaultMaskCapacity = 36
const multiTextureMaskCapacity = 32

export function countClippingMaskGroups(
  masks: Int32Array[],
  maskCounts: Int32Array,
): number {
  const groups = new Set<string>()

  for (let drawableIndex = 0; drawableIndex < maskCounts.length; drawableIndex++) {
    const count = maskCounts[drawableIndex]
    if (count <= 0) continue

    const maskIds = Array.from(masks[drawableIndex].subarray(0, count))
    maskIds.sort((left, right) => left - right)
    groups.add(maskIds.join(','))
  }

  return groups.size
}

export function requiredMaskRenderTextureCount(maskGroupCount: number): number {
  if (maskGroupCount <= defaultMaskCapacity) return 1
  return Math.ceil(maskGroupCount / multiTextureMaskCapacity)
}
