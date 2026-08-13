function getPetBounds(workArea) {
  return {
    x: Math.round(workArea.x),
    y: Math.round(workArea.y),
    width: Math.max(1, Math.round(workArea.width)),
    height: Math.max(1, Math.round(workArea.height)),
  }
}

function isPointInPetRegions(point, regions) {
  if (!point || !Array.isArray(regions)) return false
  return regions.some(region => {
    if (!region) return false
    const x = Number(region.x)
    const y = Number(region.y)
    const width = Number(region.width)
    const height = Number(region.height)
    if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
      return false
    }
    return point.x >= x && point.x <= x + width
      && point.y >= y && point.y <= y + height
  })
}

function fitBoundsToWorkArea(bounds, workArea) {
  const width = Math.min(bounds.width, workArea.width)
  const height = Math.min(bounds.height, workArea.height)
  return {
    x: Math.min(
      workArea.x + workArea.width - width,
      Math.max(workArea.x, bounds.x),
    ),
    y: Math.min(
      workArea.y + workArea.height - height,
      Math.max(workArea.y, bounds.y),
    ),
    width,
    height,
  }
}

function selectRestorableBounds({ current, normal, maximized, fullScreen }) {
  return maximized || fullScreen ? normal : current
}

module.exports = {
  fitBoundsToWorkArea,
  getPetBounds,
  isPointInPetRegions,
  selectRestorableBounds,
}
