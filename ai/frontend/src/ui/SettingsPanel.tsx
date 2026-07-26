import { useState } from 'react'
import { theme } from '../core/theme'
import type { AppSettings } from '../core/store'
import { electronWindowBridge } from '../session/electron-window-bridge'

export interface SettingsPanelProps {
  open: boolean
  onClose: () => void
  embedded?: boolean
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
  /** Accessory parts: label -> partId */
  accessoryParts?: Record<string, string>
  /** Current accessory state: label -> enabled */
  accessoryState?: Record<string, boolean>
  /** Called when user toggles an accessory */
  onAccessoryToggle?: (label: string) => void
}

const CHARACTERS = [
  { id: 'monika', label: 'Monika' },
]

const LIVE2D_MODELS = [
  { id: 'Design_genius_White', label: 'Design Genius White' },
  { id: 'youxiaomiao', label: 'You Xiaomiao' },
  { id: 'ariu', label: 'Ariu' },
  { id: 'mao_zh-Hans', label: 'Mao (CN)' },
]

const LIVE2D_TOGGLES = [
  { key: 'live2dBlink' as const, label: 'Auto Blink', desc: 'Automatic eye blinking animation' },
  { key: 'live2dBreathe' as const, label: 'Breathing', desc: 'Body sway and breathing motion' },
  { key: 'live2dLipSync' as const, label: 'Lip Sync', desc: 'Mouth movement during speech' },
  { key: 'live2dHeadTracking' as const, label: 'Head Tracking', desc: 'Follow cursor with head and eyes' },
  { key: 'live2dExpression' as const, label: 'Expressions', desc: 'Facial expression presets' },
  { key: 'live2dIdle' as const, label: 'Idle Animation', desc: 'All idle movements combined' },
]

type TabId = 'general' | 'animation' | 'appearance' | 'about'

interface TabDef {
  id: TabId
  label: string
  icon: string
}

const TABS: TabDef[] = [
  { id: 'general', label: 'General', icon: '⚙' },
  { id: 'animation', label: 'Animation', icon: '✦' },
  { id: 'appearance', label: 'Appearance', icon: '◈' },
  { id: 'about', label: 'About', icon: 'ℹ' },
]

const isElectron = electronWindowBridge.available

export function SettingsPanel({
  open,
  onClose,
  embedded = false,
  settings,
  onSettingChange,
  accessoryParts,
  accessoryState,
  onAccessoryToggle,
}: SettingsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('general')

  if (!open) return null

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  const panel = (
      <div style={embedded ? styles.embedded : styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>Settings</span>
          {!embedded && <button type="button" style={styles.closeBtn} onClick={onClose}>&times;</button>}
        </div>

        <div style={styles.body}>
          {/* Tab sidebar */}
          <div style={styles.tabBar}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                style={{
                  ...styles.tabBtn,
                  backgroundColor: activeTab === tab.id ? theme.colors.bg.surface : 'transparent',
                  borderLeft: activeTab === tab.id ? `2px solid ${theme.colors.accent}` : '2px solid transparent',
                }}
                onClick={() => setActiveTab(tab.id)}
              >
                <span style={styles.tabIcon}>{tab.icon}</span>
                <span style={styles.tabLabel}>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={styles.content}>
            {activeTab === 'general' && (
              <GeneralTab settings={settings} onSettingChange={onSettingChange} />
            )}
            {activeTab === 'animation' && (
              <AnimationTab settings={settings} onSettingChange={onSettingChange} />
            )}
            {activeTab === 'appearance' && (
              <AppearanceTab
                accessoryParts={accessoryParts}
                accessoryState={accessoryState}
                onAccessoryToggle={onAccessoryToggle}
              />
            )}
            {activeTab === 'about' && <AboutTab />}
          </div>
        </div>
      </div>
  )

  if (embedded) return panel

  return (
    <div style={styles.overlay} onClick={handleOverlayClick}>
      {panel}
    </div>
  )
}

// ── Tab: General ──

function GeneralTab({ settings, onSettingChange }: {
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
}) {
  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Character</div>

      <SettingRow label="Character">
        <select
          style={styles.select}
          value={settings.activeCharacterId}
          onChange={(e) => onSettingChange('activeCharacterId', e.target.value)}
        >
          {CHARACTERS.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
      </SettingRow>

      <SettingRow label="Live2D Model">
        <select
          style={styles.select}
          value={settings.live2dModel}
          onChange={(e) => onSettingChange('live2dModel', e.target.value)}
        >
          {LIVE2D_MODELS.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      </SettingRow>

      <div style={styles.divider} />
      <div style={styles.sectionLabel}>Window</div>

      <SettingRow label="Window Mode" desc="Pet mode removes window frame">
        <select
          style={styles.select}
          value={settings.windowMode}
          onChange={(e) => onSettingChange('windowMode', e.target.value as 'window' | 'pet')}
        >
          <option value="window">Window</option>
          <option value="pet">Pet</option>
        </select>
      </SettingRow>

      <SettingRow label="Always on Top" desc={isElectron ? '' : 'Desktop app only'}>
        <Toggle
          checked={settings.alwaysOnTop}
          disabled={!isElectron}
          onChange={(v) => onSettingChange('alwaysOnTop', v)}
        />
      </SettingRow>

      <div style={styles.divider} />
      <div style={styles.sectionLabel}>Interaction</div>

      <SettingRow label="Proactive Mode" desc="AI initiates conversation">
        <Toggle
          checked={settings.proactive}
          onChange={(v) => onSettingChange('proactive', v)}
        />
      </SettingRow>
      {settings.proactive && (
        <div style={styles.proactiveIdleRow}>
          <span style={styles.proactiveIdleLabel}>Idle time:</span>
          <div style={styles.proactiveIdleButtons}>
            {[
              { label: '30s', value: 30 },
              { label: '1min', value: 60 },
              { label: '2min', value: 120 },
              { label: '5min', value: 300 },
              { label: '10min', value: 600 },
            ].map((opt) => (
              <button
                key={opt.value}
                type="button"
                style={{
                  ...styles.proactiveIdleBtn,
                  backgroundColor: settings.proactiveIdleTime === opt.value
                    ? theme.colors.accent
                    : theme.colors.bg.surface,
                  color: settings.proactiveIdleTime === opt.value
                    ? '#fff'
                    : theme.colors.text.primary,
                }}
                onClick={() => onSettingChange('proactiveIdleTime', opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <SettingRow label="Voice Input" desc="Enable microphone for voice chat">
        <Toggle
          checked={settings.voiceInputEnabled}
          onChange={(v) => onSettingChange('voiceInputEnabled', v)}
        />
      </SettingRow>
    </div>
  )
}

// ── Tab: Animation ──

function AnimationTab({ settings, onSettingChange }: {
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
}) {
  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Live2D Components</div>
      <div style={styles.sectionDesc}>Toggle individual character animation features</div>

      <div style={styles.toggleCards}>
        {LIVE2D_TOGGLES.map(({ key, label, desc }) => (
          <div key={key} style={styles.toggleCard}>
            <div style={styles.toggleCardInfo}>
              <span style={styles.toggleCardLabel}>{label}</span>
              <span style={styles.toggleCardDesc}>{desc}</span>
            </div>
            <Toggle
              checked={settings[key]}
              onChange={(v) => onSettingChange(key, v)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tab: Appearance (Accessories) ──

function AppearanceTab({
  accessoryParts,
  accessoryState,
  onAccessoryToggle,
}: {
  accessoryParts?: Record<string, string>
  accessoryState?: Record<string, boolean>
  onAccessoryToggle?: (label: string) => void
}) {
  const parts = accessoryParts ? Object.keys(accessoryParts) : []

  if (parts.length === 0) {
    return (
      <div style={styles.tabContent}>
        <div style={styles.sectionLabel}>Accessories</div>
        <div style={styles.emptyState}>No accessories available for this model</div>
      </div>
    )
  }

  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Accessories</div>
      <div style={styles.sectionDesc}>Toggle model accessories on/off</div>

      <div style={styles.toggleCards}>
        {parts.map((label) => (
          <div key={label} style={styles.toggleCard}>
            <div style={styles.toggleCardInfo}>
              <span style={styles.toggleCardLabel}>{label}</span>
            </div>
            <Toggle
              checked={accessoryState?.[label] ?? true}
              onChange={() => onAccessoryToggle?.(label)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tab: About ──

function AboutTab() {
  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Monika Companion</div>
      <div style={styles.aboutDesc}>
        A virtual companion powered by AI with Live2D character rendering.
      </div>
      <div style={styles.divider} />
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Version</span>
        <span style={styles.aboutValue}>0.1.0</span>
      </div>
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Renderer</span>
        <span style={styles.aboutValue}>Live2D Cubism 4</span>
      </div>
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Engine</span>
        <span style={styles.aboutValue}>WebGL</span>
      </div>
    </div>
  )
}

// ── Shared components ──

function SettingRow({ label, desc, children }: {
  label: string
  desc?: string
  children: React.ReactNode
}) {
  return (
    <div style={styles.settingRow}>
      <div style={styles.settingInfo}>
        <span style={styles.settingLabel}>{label}</span>
        {desc && <span style={styles.settingDesc}>{desc}</span>}
      </div>
      {children}
    </div>
  )
}

function Toggle({ checked, disabled, onChange }: {
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label style={{ ...styles.toggleWrap, opacity: disabled ? 0.4 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>
      <input
        type="checkbox"
        style={styles.toggleInput}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span style={{
        ...styles.toggleTrack,
        backgroundColor: checked ? theme.colors.accent : '#3a3a3e',
      }}>
        <span style={{
          ...styles.toggleThumb,
          transform: checked ? 'translateX(18px)' : 'translateX(2px)',
        }} />
      </span>
    </label>
  )
}

// ── Styles ──

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, backgroundColor: 'rgba(0, 0, 0, 0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: theme.zIndex.modal,
  },
  modal: {
    width: 560, maxWidth: '95vw', maxHeight: '85vh',
    backgroundColor: theme.colors.bg.root, border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radius.lg, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
  },
  embedded: {
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: theme.colors.bg.root,
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: `${theme.spacing.lg}px ${theme.spacing.xl}px`,
    borderBottom: `1px solid ${theme.colors.border}`, flexShrink: 0,
  },
  title: { fontSize: theme.fontSize.lg, fontWeight: theme.fontWeight.semibold, color: theme.colors.text.primary },
  closeBtn: {
    width: 30, height: 30, borderRadius: theme.radius.sm, border: 'none',
    backgroundColor: 'transparent', color: theme.colors.text.secondary,
    fontSize: '1.3rem', cursor: 'pointer', display: 'flex', alignItems: 'center',
    justifyContent: 'center', lineHeight: 1, padding: 0,
  },
  body: {
    display: 'flex', flex: 1, overflow: 'hidden',
  },

  // ── Tab bar (left sidebar) ──
  tabBar: {
    width: 120, flexShrink: 0, display: 'flex', flexDirection: 'column',
    padding: `${theme.spacing.md}px 0`, gap: 2,
    borderRight: `1px solid ${theme.colors.border}`,
    backgroundColor: theme.colors.bg.surface,
  },
  tabBtn: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '10px 14px', border: 'none', cursor: 'pointer',
    color: theme.colors.text.secondary, fontSize: theme.fontSize.sm,
    textAlign: 'left' as const, transition: 'background-color 0.1s',
    width: '100%',
  },
  tabIcon: { fontSize: '1rem', flexShrink: 0, width: 20, textAlign: 'center' as const },
  tabLabel: { whiteSpace: 'nowrap' as const },

  // ── Content area ──
  content: {
    flex: 1, overflowY: 'auto', padding: `${theme.spacing.lg}px ${theme.spacing.xl}px`,
  },
  tabContent: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.md,
  },

  // ── Section labels ──
  sectionLabel: {
    fontSize: theme.fontSize.xs, fontWeight: theme.fontWeight.semibold,
    color: theme.colors.text.muted, textTransform: 'uppercase' as const,
    letterSpacing: '0.08em', marginTop: theme.spacing.xs,
  },
  sectionDesc: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted,
    marginTop: -theme.spacing.sm,
  },
  divider: {
    height: 1, backgroundColor: theme.colors.border,
    margin: `${theme.spacing.xs}px 0`,
  },
  emptyState: {
    fontSize: theme.fontSize.sm, color: theme.colors.text.muted,
    padding: `${theme.spacing.xl}px 0`, textAlign: 'center' as const,
  },

  // ── Setting row ──
  settingRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: theme.spacing.lg, minHeight: 36,
  },
  settingInfo: { display: 'flex', flexDirection: 'column', gap: 1 },
  settingLabel: { fontSize: theme.fontSize.md, fontWeight: theme.fontWeight.medium, color: theme.colors.text.primary },
  settingDesc: { fontSize: theme.fontSize.xs, color: theme.colors.text.muted, marginTop: 1 },
  select: {
    padding: `${theme.spacing.xs}px ${theme.spacing.md}px`, borderRadius: theme.radius.md,
    border: `1px solid ${theme.colors.border}`, backgroundColor: theme.colors.bg.surface,
    color: theme.colors.text.primary, fontSize: theme.fontSize.sm, outline: 'none',
    cursor: 'pointer', minWidth: 120, flexShrink: 0,
  },

  // ── Toggle cards ──
  toggleCards: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.xs,
  },
  toggleCard: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: `${theme.spacing.sm}px ${theme.spacing.md}px`,
    backgroundColor: theme.colors.bg.surface,
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.colors.border}`,
    gap: theme.spacing.md,
  },
  toggleCardInfo: {
    display: 'flex', flexDirection: 'column', gap: 1, flex: 1,
  },
  toggleCardLabel: {
    fontSize: theme.fontSize.sm, fontWeight: theme.fontWeight.medium,
    color: theme.colors.text.primary,
  },
  toggleCardDesc: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted,
  },

  // ── About tab ──
  aboutDesc: {
    fontSize: theme.fontSize.sm, color: theme.colors.text.secondary,
    lineHeight: 1.5,
  },
  aboutRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '6px 0',
  },
  aboutKey: { fontSize: theme.fontSize.sm, color: theme.colors.text.secondary },
  aboutValue: { fontSize: theme.fontSize.sm, color: theme.colors.text.primary, fontWeight: theme.fontWeight.medium },

  // ── Proactive idle time ──
  proactiveIdleRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: theme.spacing.md, paddingLeft: theme.spacing.lg,
  },
  proactiveIdleLabel: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted, whiteSpace: 'nowrap',
  },
  proactiveIdleButtons: {
    display: 'flex', gap: 4,
  },
  proactiveIdleBtn: {
    padding: '3px 8px', borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`,
    fontSize: theme.fontSize.xs, cursor: 'pointer',
    transition: 'all 0.12s',
  },

  // ── Toggle switch ──
  toggleWrap: { position: 'relative' as const, display: 'inline-block', flexShrink: 0 },
  toggleInput: { position: 'absolute' as const, opacity: 0, width: 0, height: 0, margin: 0 },
  toggleTrack: {
    display: 'inline-block', width: 40, height: 22, borderRadius: 11,
    transition: 'background-color 0.15s', position: 'relative' as const,
  },
  toggleThumb: {
    display: 'inline-block', width: 18, height: 18, borderRadius: '50%',
    backgroundColor: '#f0f0f0', position: 'absolute' as const, top: 2, left: 0,
    transition: 'transform 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
  },
}
