import type { ReactNode } from 'react'

export function DrawerPanel({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="drawer-panel">
      <header className="drawer-header">
        <h2>{title}</h2>
        {action}
      </header>
      <div className="drawer-body">{children}</div>
    </section>
  )
}

export function DeferredDrawer({ title, description }: { title: string; description: string }) {
  return (
    <DrawerPanel title={title}>
      <div className="deferred-drawer">
        <span>已预留</span>
        <p>{description}</p>
      </div>
    </DrawerPanel>
  )
}
