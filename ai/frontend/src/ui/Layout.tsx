import { useEffect, useState, type ReactNode } from 'react'

export type WorkspaceSection = 'chat' | 'history' | 'system' | 'settings'

export interface LayoutProps {
  statusBar: ReactNode
  characterArea: ReactNode
  chatArea: ReactNode
  inputBar: ReactNode
  systemArea: ReactNode
  activeSection: WorkspaceSection
  onSectionChange: (section: WorkspaceSection) => void
}

const readCollapsed = (key: string) => localStorage.getItem(key) === 'true'

export function Layout({
  statusBar,
  characterArea,
  chatArea,
  inputBar,
  systemArea,
  activeSection,
  onSectionChange,
}: LayoutProps) {
  const [navCollapsed, setNavCollapsed] = useState(() => readCollapsed('ui.nav.collapsed'))
  const [systemCollapsed, setSystemCollapsed] = useState(() => readCollapsed('ui.system.collapsed'))

  useEffect(() => localStorage.setItem('ui.nav.collapsed', String(navCollapsed)), [navCollapsed])
  useEffect(() => localStorage.setItem('ui.system.collapsed', String(systemCollapsed)), [systemCollapsed])

  const navItems: Array<{ id: WorkspaceSection; label: string; short: string }> = [
    { id: 'chat', label: '对话', short: '聊' },
    { id: 'history', label: '记忆', short: '忆' },
    { id: 'system', label: '系统', short: '状' },
    { id: 'settings', label: '设置', short: '设' },
  ]

  return (
    <div className="workspace-shell">
      <div className="workspace-main">
        <aside className={`nav-rail ${navCollapsed ? 'is-collapsed' : ''}`} aria-label="主导航">
          <div className="brand">
            <span className="brand-mark">S</span>
            {!navCollapsed && <span className="brand-name">SoulLink</span>}
          </div>
          <nav className="nav-items">
            {navItems.map(item => (
              <button
                key={item.id}
                type="button"
                className={`nav-item ${activeSection === item.id ? 'is-active' : ''}`}
                onClick={() => onSectionChange(item.id)}
                title={navCollapsed ? item.label : undefined}
              >
                <span className="nav-item-mark">{item.short}</span>
                {!navCollapsed && <span>{item.label}</span>}
              </button>
            ))}
          </nav>
          <button
            type="button"
            className="rail-collapse"
            onClick={() => setNavCollapsed(value => !value)}
            aria-label={navCollapsed ? '展开导航' : '收起导航'}
          >
            {navCollapsed ? '展开' : '收起'}
          </button>
        </aside>

        <main className="companion-stage">
          <div className="character-stage">{characterArea}</div>
          <section className="conversation-dock" aria-label="对话区">
            {chatArea}
            {inputBar}
          </section>
        </main>

        <aside className={`system-rail ${systemCollapsed ? 'is-collapsed' : ''}`} aria-label="实时状态">
          <button
            type="button"
            className="system-collapse"
            onClick={() => setSystemCollapsed(value => !value)}
            aria-label={systemCollapsed ? '展开实时状态' : '收起实时状态'}
          >
            {systemCollapsed ? '状态' : '收起'}
          </button>
          {!systemCollapsed && systemArea}
        </aside>
      </div>
      {statusBar}
    </div>
  )
}
