const PET_MARGIN = 24

function getPetBounds(workArea) {
  const marginX = Math.min(PET_MARGIN, Math.max(0, Math.floor((workArea.width - 1) / 2)))
  const marginY = Math.min(PET_MARGIN, Math.max(0, Math.floor((workArea.height - 1) / 2)))
  const availableWidth = Math.max(1, workArea.width - marginX * 2)
  const availableHeight = Math.max(1, workArea.height - marginY * 2)
  const width = Math.min(availableWidth, 440, Math.max(320, Math.round(workArea.width * 0.32)))
  const height = Math.min(availableHeight, 680, Math.max(480, Math.round(workArea.height * 0.72)))
  return {
    x: workArea.x + workArea.width - width - marginX,
    y: workArea.y + workArea.height - height - marginY,
    width,
    height,
  }
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

module.exports = { fitBoundsToWorkArea, getPetBounds, selectRestorableBounds }
