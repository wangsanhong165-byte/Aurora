// Shared window-drag state. The title bar sets this while a frameless-window
// drag is active so heavy renderer work (Live2D canvas re-fit) can be paused.
// During a drag the window size is pinned by the main process, so re-measuring
// and resizing the stage canvas would only churn the renderer and make the
// model flicker as the reported size jitters by a pixel or two.
let dragging = false

export function setWindowDragging(value: boolean): void {
  dragging = value
}

export function isWindowDragging(): boolean {
  return dragging
}
