interface ResizeObserverLike {
  observe(element: object): void
  disconnect(): void
}

type ResizeObserverConstructor = new (callback: () => void) => ResizeObserverLike

export function observeElementResize(
  element: object,
  onResize: () => void,
  Observer: ResizeObserverConstructor = ResizeObserver as unknown as ResizeObserverConstructor,
): () => void {
  const observer = new Observer(onResize)
  observer.observe(element)
  return () => observer.disconnect()
}
